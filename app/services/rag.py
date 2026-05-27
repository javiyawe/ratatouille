import json
import uuid
from typing import Optional

from app.database import get_col, get_chunk_col
from app.config import SYSTEM_PROMPT
import logging
from app.services.llm import embed, llm

def build_embed_text(r: dict) -> str:
    """Construye un texto enriquecido para embeddings, incluyendo ingredientes para mejorar la búsqueda."""
    ingredientes = ", ".join([i.get("nombre", "") for i in r.get("ingredientes", [])])
    parts = [
        f"Título: {r.get('titulo', '')}",
        f"Descripción: {r.get('descripcion', '')}",
        f"Tipo de cocina: {r.get('tipo_cocina', '')}",
        f"Ingredientes: {ingredientes}",
        f"Etiquetas: {', '.join(r.get('etiquetas', []))}"
    ]
    return " | ".join(p for p in parts if p)


def build_where(max_time: Optional[int], difficulty: Optional[str]) -> Optional[dict]:
    conditions = []
    if max_time:
        conditions.append({"total_time_minutes": {"$lte": max_time}})
    if difficulty:
        conditions.append({"dificultad": {"$eq": difficulty}})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def normalize_recipe(r: dict) -> dict:
    if not r.get("titulo"):
        r["titulo"] = r.get("nombre") or r.get("receta") or r.get("title") or r.get("plato") or "Receta sin nombre"
    if not r.get("ingredientes"):
        r["ingredientes"] = []
    if not r.get("pasos"):
        r["pasos"] = []
    return r

def build_recipe_chunks(doc_id: str, recipe: dict) -> list[tuple[str, str, dict]]:
    """Devuelve lista de (chunk_id, text, metadata) para una receta."""
    chunks = []
    base_meta = {
        "recipe_id": doc_id,
        "titulo": str(recipe.get("titulo", "Sin título")),
        "total_time_minutes": int((recipe.get("tiempos") or {}).get("total_minutos", 0)),
        "dificultad": str(recipe.get("dificultad", "Media")),
    }
    
    # Chunk 1: Metadata y descripción
    desc_text = f"Título: {recipe.get('titulo','')}. Descripción: {recipe.get('descripcion','')}. Cocina: {recipe.get('tipo_cocina','')}. Etiquetas: {', '.join(recipe.get('etiquetas', []))}"
    chunks.append((f"{doc_id}_meta", desc_text, {**base_meta, "chunk_type": "meta"}))
    
    # Chunk 2: Ingredientes
    ingredientes = ", ".join([f"{i.get('cantidad','')} {i.get('unidad','')} {i.get('nombre','')}".strip() for i in recipe.get("ingredientes", [])])
    if ingredientes:
        chunks.append((f"{doc_id}_ingredientes", f"Ingredientes de {recipe.get('titulo','')}: {ingredientes}", {**base_meta, "chunk_type": "ingredientes"}))
    
    # Chunk 3: Pasos
    pasos = " ".join(recipe.get("pasos", []))
    if pasos:
        chunks.append((f"{doc_id}_pasos", f"Pasos para {recipe.get('titulo','')}: {pasos}", {**base_meta, "chunk_type": "pasos"}))
        
    return chunks


def safe_query(query_embedding: list, n: int, where: Optional[dict] = None) -> dict:
    total = get_chunk_col().count()
    if total == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    n = min(n, total)
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": n,
        "include": ["metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return get_chunk_col().query(**kwargs)


def parse_docs(results: dict) -> list[dict]:
    recipes = []
    if not results or not results.get("documents"):
        return []
    for i, doc in enumerate(results["documents"][0]):
        try:
            r = json.loads(doc)
            r = normalize_recipe(r)
            r["_id"] = results["ids"][0][i]
            recipes.append(r)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Error parsing document: {e}")
    return recipes


async def perform_search(
    query: str,
    n_results: int = 6,
    max_time: Optional[int] = None,
    difficulty: Optional[str] = None,
) -> list[dict]:
    """Algoritmo de búsqueda unificado: combina búsqueda semántica (embeddings) y textual."""
    total = get_col().count()
    if total == 0:
        return []

    q       = query.strip()
    q_lower = q.lower()
    words   = [w for w in q_lower.split() if len(w) >= 2]
    where   = build_where(max_time, difficulty)

    # ── 1. Búsqueda semántica vectorial (en Chunks) ─────────────────────────
    vec = await embed(q) if q else None
    sem_ids: dict[str, float] = {}   # recipe_id → similarity score
    sem_ordered: list[dict]   = []

    if vec:
        n = min(max(n_results * 3, 30), get_chunk_col().count())
        res = safe_query(vec, n, where)
        if res.get("metadatas") and res["metadatas"][0]:
            for i, meta in enumerate(res["metadatas"][0]):
                rid = meta["recipe_id"]
                score = round(1.0 - res["distances"][0][i], 4)
                # Conservamos el mejor score de los chunks para esa receta
                if rid not in sem_ids or score > sem_ids[rid]:
                    sem_ids[rid] = score
            
            # Recuperar las recetas completas ordenadas por score semántico
            if sem_ids:
                sorted_rids = sorted(sem_ids.keys(), key=lambda k: sem_ids[k], reverse=True)
                full_docs = get_col().get(ids=sorted_rids, include=["documents"])
                doc_map = {fid: json.loads(fdoc) for fid, fdoc in zip(full_docs["ids"], full_docs["documents"])}
                for rid in sorted_rids:
                    if rid in doc_map:
                        r = normalize_recipe(doc_map[rid])
                        r["_id"] = rid
                        r["_score"] = sem_ids[rid]
                        sem_ordered.append(r)

    # ── 2. Búsqueda textual sobre todos los documentos ───────────────────
    all_raw = get_col().get(limit=500, include=["documents"])
    text_hits: list[tuple[int, dict]] = []   # (score, recipe)

    for i, doc in enumerate(all_raw["documents"]):
        try:
            r = json.loads(doc)
            r = normalize_recipe(r)
            rid = all_raw["ids"][i]

            # Aplicar filtros de tiempo / dificultad
            if max_time and (r.get("tiempos") or {}).get("total_minutos", 9999) > max_time:
                continue
            if difficulty and r.get("dificultad", "") != difficulty:
                continue

            if not words:
                continue

            searchable = " ".join([
                r.get("titulo", ""),
                r.get("descripcion", ""),
                r.get("tipo_cocina", ""),
                " ".join(r.get("etiquetas", [])),
                " ".join(i2.get("nombre", "") for i2 in r.get("ingredientes", [])),
            ]).lower()

            score = 0
            for w in words:
                if w in r.get("titulo", "").lower():            score += 10
                elif any(w in e.lower() for e in r.get("etiquetas", [])): score += 8
                elif w in r.get("tipo_cocina", "").lower():     score += 6
                elif w in " ".join(i2.get("nombre","") for i2 in r.get("ingredientes",[])).lower(): score += 5
                elif w in searchable:                           score += 2

            if score > 0:
                r["_id"]    = rid
                r["_score"] = round(score / (len(words) * 10), 4)
                text_hits.append((score, r))
        except Exception:
            pass

    text_hits.sort(key=lambda x: -x[0])
    text_ordered = [r for _, r in text_hits]

    # ── 3. Fusión: ambos > solo-texto > solo-semántico ────────────────────
    text_id_set = {r["_id"] for r in text_ordered}
    seen: set[str] = set()
    merged: list[dict] = []

    for r in sem_ordered:           # semántico que también tiene match textual
        if r["_id"] in text_id_set:
            merged.append(r)
            seen.add(r["_id"])

    for r in text_ordered:          # solo texto (coincidencia exacta)
        if r["_id"] not in seen:
            merged.append(r)
            seen.add(r["_id"])

    for r in sem_ordered:           # solo semántico
        if r["_id"] not in seen:
            merged.append(r)
            seen.add(r["_id"])

    # Si no hay query ni filtros, devolver todas ordenadas
    if not q and not max_time and not difficulty:
        merged = text_ordered if text_ordered else []

    return merged[:n_results]


async def store_recipe_async(recipe: dict) -> str:
    doc_id = str(uuid.uuid4())
    # 1. Guardar receta completa (para recuperar luego)
    vector = await embed(build_embed_text(recipe)) # Keep this for legacy / list_recipes if needed, or dummy
    tiempos = recipe.get("tiempos") or {}
    metadata = {
        "titulo": str(recipe.get("titulo", "Sin título")),
        "total_time_minutes": int(tiempos.get("total_minutos", 0)),
        "dificultad": str(recipe.get("dificultad", "Media")),
    }
    get_col().add(
        ids=[doc_id],
        embeddings=[vector],
        documents=[json.dumps(recipe, ensure_ascii=False)],
        metadatas=[metadata],
    )
    
    # 2. Generar y guardar chunks para búsqueda semántica precisa
    chunks = build_recipe_chunks(doc_id, recipe)
    if chunks:
        c_ids = [c[0] for c in chunks]
        c_texts = [c[1] for c in chunks]
        c_metas = [c[2] for c in chunks]
        
        # Generar embeddings para los chunks
        c_embeds = []
        for text in c_texts:
            c_embeds.append(await embed(text))
            
        get_chunk_col().add(
            ids=c_ids,
            embeddings=c_embeds,
            documents=c_texts,
            metadatas=c_metas
        )

    return doc_id


class RAGPipeline:
    def __init__(self, n_results: int = 3):
        self.n_results = n_results

    async def retrieve(self, query: str, filters: dict = None) -> list[dict]:
        vec = await embed(query)
        where = build_where(
            filters.get("max_time") if filters else None,
            filters.get("difficulty") if filters else None,
        )
        res = safe_query(vec, self.n_results, where)
        return parse_docs(res)

    async def query(self, user_message: str, history: list[dict] = None) -> dict:
        docs = await self.retrieve(user_message)
        context = json.dumps(docs, ensure_ascii=False) if docs else ""
        msgs = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCONTEXTO:\n{context}"}]
        if history:
            msgs.extend(history[-4:])
        msgs.append({"role": "user", "content": user_message})
        msg = await llm(msgs, temperature=0.4)
        return {
            "answer": msg.get("content", ""),
            "sources": [{"id": r["_id"], "titulo": r["titulo"]} for r in docs],
        }


rag = RAGPipeline(n_results=3)

# ─────────────────────────── MCP Tools ───────────────────────────
MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_recipes",
            "description": "Busca recetas en el libro del usuario usando búsqueda semántica por ingredientes, técnica o nombre de plato",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Términos de búsqueda (ingrediente, plato, técnica culinaria)"},
                    "n":     {"type": "integer", "description": "Número máximo de resultados (1-5)", "default": 3},
                    "max_time": {"type": "integer", "description": "Tiempo máximo de preparación en minutos"},
                    "difficulty": {"type": "string", "enum": ["Fácil", "Media", "Difícil"], "description": "Dificultad de la receta"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_recipes",
            "description": "Lista todos los títulos y IDs de recetas disponibles en el libro del usuario",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recipe",
            "description": "Obtiene los detalles completos (ingredientes, pasos, tiempos) de una receta por su ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipe_id": {"type": "string", "description": "ID único de la receta"}
                },
                "required": ["recipe_id"]
            }
        }
    }
]

async def execute_tool(name: str, params: dict) -> tuple[str, list]:
    """Ejecuta una herramienta MCP. Devuelve (resultado_json, fuentes)."""
    sources = []

    if name == "search_recipes":
        query = params.get("query", "")
        n = min(int(params.get("n", 3)), 5)
        max_time = params.get("max_time")
        difficulty = params.get("difficulty")
        found = await perform_search(query, n, max_time, difficulty)
        for r in found:
            if r.get("_id"):
                sources.append({"id": r["_id"], "titulo": r["titulo"]})
        return json.dumps(found, ensure_ascii=False), sources

    elif name == "list_recipes":
        raw = get_col().get(limit=200, include=["metadatas"])
        titles = [
            {"titulo": m.get("titulo", "?"), "id": cid}
            for cid, m in zip(raw["ids"], raw["metadatas"])
        ]
        return json.dumps(titles, ensure_ascii=False), sources

    elif name == "get_recipe":
        recipe_id = params.get("recipe_id", "")
        data = get_col().get(ids=[recipe_id], include=["documents"])
        if data["documents"]:
            r = json.loads(data["documents"][0])
            sources.append({"id": recipe_id, "titulo": r.get("titulo", "?")})
            return data["documents"][0], sources
        return json.dumps({"error": "Receta no encontrada"}), sources

    return json.dumps({"error": f"Tool '{name}' desconocido"}), sources
