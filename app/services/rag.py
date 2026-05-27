import json
import uuid
from typing import Optional

from app.database import get_col
from app.config import SYSTEM_PROMPT
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


def safe_query(query_embedding: list, n: int, where: Optional[dict] = None) -> dict:
    total = get_col().count()
    if total == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    n = min(n, total)
    kwargs = {
        "query_embeddings": [query_embedding],
        "n_results": n,
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where
    return get_col().query(**kwargs)


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

    # ── 1. Búsqueda semántica vectorial ──────────────────────────────────
    vec = await embed(q) if q else None
    sem_ids: dict[str, float] = {}   # id → similarity score
    sem_ordered: list[dict]   = []

    if vec:
        n = min(max(n_results, 30), total)
        res = safe_query(vec, n, where)
        if res.get("documents") and res["documents"][0]:
            for i, doc in enumerate(res["documents"][0]):
                try:
                    r = json.loads(doc)
                    r = normalize_recipe(r)
                    r["_id"]    = res["ids"][0][i]
                    r["_score"] = round(1.0 - res["distances"][0][i], 4)
                    sem_ids[r["_id"]] = r["_score"]
                    sem_ordered.append(r)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Error parsing semantic result: {e}")

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
    vector = await embed(build_embed_text(recipe))
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
