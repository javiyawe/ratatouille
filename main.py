"""
Ratatui — Recetario Inteligente con IA Agéntica
Backend FastAPI con RAG, ChromaDB, Ollama y MCP.

Arranque:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import json
import re
import sqlite3
import uuid
import time
from pathlib import Path
from typing import Optional

import httpx
import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─────────────────────────── Configuración ────────────────────────────

OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text:latest"  # Rápido y ligero
LLM_MODEL   = "qwen2.5:1.5b"             # Respuesta instantánea y eficiente

try:
    with open("training_data.json", encoding="utf-8") as _f:
        _TRAINING = json.load(_f)
    TRAINING_PAIRS: list[dict] = _TRAINING.get("training_pairs", [])
except FileNotFoundError:
    TRAINING_PAIRS = []

app = FastAPI(title="Ratatui API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_chroma = chromadb.PersistentClient(path="./chroma_db")

def get_col():
    try:
        col = _chroma.get_collection(name="recipes")
        # Realizamos una consulta mínima de prueba para validar compatibilidad de dimensiones
        # nomic-embed-text tiene 768 dimensiones, bge-m3 tiene 1024.
        dim = 768 if EMBED_MODEL == "nomic-embed-text:latest" else 1024
        if col.count() > 0:
            col.query(query_embeddings=[[0.0] * dim], n_results=1)
        return col
    except Exception:
        # Si ocurre un error (por ejemplo, Embedding dimension mismatch tras cambiar el modelo),
        # borramos y recreamos la colección para evitar cuelgues.
        try:
            _chroma.delete_collection(name="recipes")
        except Exception:
            pass
        return _chroma.create_collection(
            name="recipes",
            metadata={"hnsw:space": "cosine"},
        )

# ─────────────────────────── Chat Storage (SQLite) ────────────────────
# Los chats no necesitan búsqueda vectorial — SQLite es más rápido y limpio.

_CHAT_DB = Path("./chats.db")

def _chat_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_CHAT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def _init_chat_db() -> None:
    with _chat_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'Nueva conversación',
                history    TEXT NOT NULL DEFAULT '[]',
                updated_at INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()

_init_chat_db()

# Migración única: importar chats existentes de ChromaDB → SQLite
def _migrate_chats_from_chroma() -> None:
    try:
        col = _chroma.get_collection("chats")
        data = col.get(include=["documents", "metadatas"])
        if not data["ids"]:
            return
        with _chat_conn() as conn:
            for i, cid in enumerate(data["ids"]):
                title      = data["metadatas"][i].get("title", "Chat")
                updated_at = data["metadatas"][i].get("updated_at", 0)
                history    = data["documents"][i] if data["documents"] else "[]"
                conn.execute(
                    "INSERT OR IGNORE INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                    (cid, title, history, updated_at),
                )
            conn.commit()
    except Exception:
        pass   # la colección no existe o ya se migró

_migrate_chats_from_chroma()

# ─────────────────────────── Helpers Ollama ───────────────────────────

async def embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]


async def llm(messages: list[dict], temperature: float = 0.7, tools: list = None) -> dict:
    """Llamada LLM sin stream. Devuelve el dict 'message' completo (con tool_calls si los hay)."""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "top_p": 0.95},
    }
    if tools:
        payload["tools"] = tools
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]


async def llm_stream(messages: list[dict], temperature: float = 0.7):
    """Generador para streaming de tokens desde Ollama."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temperature, "top_p": 0.95},
            },
        ) as response:
            async for line in response.aiter_lines():
                if line:
                    chunk = json.loads(line)
                    if not chunk.get("done"):
                        yield chunk["message"]["content"]
                    else:
                        yield "\n\n[DONE]"

# ─────────────────────────── Modelos Pydantic ─────────────────────────

class SearchRequest(BaseModel):
    query: str
    n_results: int = 6
    max_time: Optional[int] = None
    difficulty: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None

class ChatSessionCreate(BaseModel):
    title: str = "Nueva conversación"

class ExtractRequest(BaseModel):
    text: str

class SaveRecipeRequest(BaseModel):
    recipe: dict

class UpdateRecipeRequest(BaseModel):
    recipe: dict

class RefineRecipeRequest(BaseModel):
    recipe: dict
    instructions: str

class MCPCallRequest(BaseModel):
    tool: str
    params: dict = {}

class UpdateChatTitleRequest(BaseModel):
    title: str

class TrainingCompareRequest(BaseModel):
    question: str

# ─────────────────────────── MCP Tool Definitions ─────────────────────
# MCP (Model Context Protocol): expone herramientas que la IA puede invocar
# de forma autónoma para conectarse con la base de datos de recetas.

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

# ─────────────────────────── RAG Pipeline (empaquetado) ───────────────
# RAG encapsulado como clase reutilizable para integraciones externas.

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

# ─────────────────────────── System Prompt ───────────────────────────

SYSTEM_PROMPT = """Eres Ratatui, el asistente culinario personal del usuario. Tienes acceso a su recetario privado mediante herramientas de búsqueda.

## CUÁNDO USAR HERRAMIENTAS
Usa `search_recipes` siempre que el usuario mencione:
- Ingredientes ("pollo", "pasta", "huevos", "zanahoria"…)
- Tipos de plato o cocina ("postre", "sopa", "italiano", "japonés"…)
- Restricciones o preferencias ("vegano", "sin gluten", "rápido", "fácil"…)
- Cualquier pregunta sobre qué cocinar o cómo preparar algo

NO uses herramientas para saludos, preguntas generales no culinarias o conversión de unidades.

## REGLAS CRÍTICAS DE CONTEXTO Y ALUCINACIONES (OBLIGATORIO)
1. NO TE INVENTES RECETAS. Solo puedes detallar, enumerar o sugerir recetas que estén explícitamente presentes en el contexto provisto (es decir, las recetas de su recetario obtenidas mediante las herramientas o la búsqueda).
2. Si el usuario te pide una receta específica que NO está en su libro de recetas (no aparece en el contexto), debes responder explícitamente diciendo que no tienes esa receta en su recetario. Puedes ofrecer consejos generales sobre cómo prepararla de forma culinaria general, pero aclarando siempre que es una explicación general y no una receta de su libro.
3. REFERENCIA SIEMPRE CORRECTAMENTE: Al mencionar o recomendar cualquier receta del libro, acompáñala obligatoriamente de su número de referencia entre corchetes (ej. `[1]`, `[2]`).

## ESTILO DE RESPUESTA
- Responde siempre en español
- Sé cálido, directo y experto en cocina
- Usa markdown para estructurar (## Ingredientes, ## Preparación, listas con -)
- Adapta el nivel de detalle a lo que pide el usuario: si pide una sugerencia rápida, no escribas la receta entera
"""

EXTRACTION_SCHEMA = """{
  "titulo": "string",
  "descripcion": "string",
  "tipo_cocina": "Española|Italiana|Francesa|Japonesa|Mexicana|etc",
  "dificultad": "Fácil|Media|Difícil",
  "porciones": number,
  "tiempos": {"total_minutos": number},
  "ingredientes": [{"nombre": "string", "cantidad": "string", "unidad": "string"}],
  "pasos": ["string"],
  "etiquetas": ["string"]
}"""

# ─────────────────────────── Utilidades ───────────────────────────────

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
        except:
            pass
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
        for i, doc in enumerate(res["documents"][0]):
            try:
                r = json.loads(doc)
                r = normalize_recipe(r)
                r["_id"]    = res["ids"][0][i]
                r["_score"] = round(1.0 - res["distances"][0][i], 4)
                sem_ids[r["_id"]] = r["_score"]
                sem_ordered.append(r)
            except:
                pass

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
        except:
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

def extract_json(text: str) -> dict:
    """Extrae JSON de texto LLM de forma robusta (con fallbacks)."""
    try:
        return json.loads(text.strip())
    except:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    raise ValueError("No se pudo extraer JSON de la respuesta del LLM")

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

# ─────────────────────────── Endpoints ───────────────────────────────

@app.get("/api/stats")
async def stats():
    return {"total_recipes": get_col().count()}

@app.get("/api/recipes")
async def get_recipes(limit: int = 200):
    if get_col().count() == 0:
        return {"recipes": []}
    raw = get_col().get(limit=limit, include=["documents", "metadatas"])
    recipes = []
    for i, doc in enumerate(raw["documents"]):
        try:
            r = json.loads(doc)
            r["_id"] = raw["ids"][i]
            recipes.append(normalize_recipe(r))
        except:
            pass
    return {"recipes": recipes}

@app.post("/api/search")
async def search(req: SearchRequest):
    recipes = await perform_search(
        query=req.query,
        n_results=req.n_results,
        max_time=req.max_time,
        difficulty=req.difficulty,
    )
    return {"recipes": recipes, "query": req.query}

# ─── Chat con IA Agéntica (background task + SSE) ─────────────────────

def _sse(event_type: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': event_type, **kwargs}, ensure_ascii=False)}\n\n"

# chat_id → (task, queue)  — tareas activas en curso
_active: dict[str, tuple[asyncio.Task, asyncio.Queue]] = {}

async def async_update_title(
    chat_id: str,
    message: str,
    full_ai: str,
    _wh: list,
    _db_exists: bool,
    out: asyncio.Queue,
) -> None:
    """Genera un título descriptivo en segundo plano sin bloquear la respuesta del chat."""
    try:
        ctx = f"Pregunta: {message}"
        if full_ai:
            ctx += f"\nRespuesta: {full_ai[:300]}"
        t_msg = await llm([
            {"role": "system", "content": (
                "Genera un título de 3-5 palabras para esta conversación culinaria. "
                "Sé específico: menciona el plato, ingrediente o técnica principal. "
                "Solo el texto, sin comillas ni puntos finales."
            )},
            {"role": "user", "content": ctx},
        ], temperature=0.2)
        chat_title = t_msg.get("content", message[:40]).strip().strip('"').strip(".")
    except Exception:
        chat_title = message[:40]

    try:
        with _chat_conn() as conn:
            if _db_exists:
                conn.execute(
                    "UPDATE chats SET title=?, history=?, updated_at=? WHERE id=?",
                    (chat_title, json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                )
            else:
                conn.execute(
                    "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                    (chat_id, chat_title, json.dumps(_wh, ensure_ascii=False), int(time.time())),
                )
            conn.commit()
        await out.put(_sse("title", value=chat_title))
    except Exception:
        pass
    finally:
        await out.put(None)
        _active.pop(chat_id, None)


async def _process_chat(
    chat_id: str,
    message: str,
    history: list,
    is_new: bool,
    old_title: str,
    out: asyncio.Queue,
) -> None:
    """
    Procesa el mensaje, hace streaming a 'out' y guarda el historial en DB.
    Se ejecuta como tarea independiente para asegurar completitud.
    """
    full_ai  = ""
    _src: list[dict] = []

    # ── Guardar el mensaje del usuario en la BD inmediatamente ──────────
    _wh = history + [{"role": "user", "content": message}]
    _db_exists = not is_new
    try:
        with _chat_conn() as conn:
            if is_new:
                conn.execute(
                    "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                    (chat_id, old_title or "Nueva conversación",
                     json.dumps(_wh, ensure_ascii=False), int(time.time())),
                )
                _db_exists = True
            else:
                conn.execute(
                    "UPDATE chats SET history=?, updated_at=? WHERE id=?",
                    (json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                )
            conn.commit()
    except Exception:
        pass

    async def emit(t: str, **kw):
        await out.put(_sse(t, **kw))

    try:
        # 1. Comprobar si es saludo o texto conversacional simple (bypass rápido)
        is_greeting = bool(re.search(
            r"\b(hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches|que\s+tal|cómo\s+estás|como\s+estas|gracias|muchas\s+gracias|adiós|adios|chao|saludos)\b",
            message, re.IGNORECASE
        )) and len(message) < 50

        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-10:]:
            msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": message})

        if is_greeting:
            await emit("thought", value="Saludando...")
            # Llamada de streaming directa rápida
            async for chunk in llm_stream(msgs, temperature=0.5):
                if chunk == "\n\n[DONE]":
                    break
                elif chunk:
                    full_ai += chunk
                    await emit("token", value=chunk)
            await emit("done")

        else:
            # 2. Consulta normal. Llamamos al LLM con herramientas
            await emit("thought", value="Analizando consulta...")
            agent_msg  = await llm(msgs, temperature=0.2, tools=MCP_TOOLS)
            content    = agent_msg.get("content") or ""
            tool_calls = agent_msg.get("tool_calls") or []

            if tool_calls:
                # El modelo solicitó herramientas (ej. buscar o detallar receta)
                msgs.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                all_sources = []
                for tc in tool_calls:
                    func        = tc.get("function", {})
                    tool_name   = func.get("name", "")
                    raw_args    = func.get("arguments", {})
                    tool_params = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")

                    if tool_name == "search_recipes":
                        label = f"Buscando «{tool_params.get('query','…')}» en el recetario"
                    elif tool_name == "get_recipe":
                        label = "Consultando detalles de la receta"
                    else:
                        label = tool_name.replace("_", " ").capitalize()

                    await emit("thought", value=f"{label}…")
                    result_str, sources = await execute_tool(tool_name, tool_params)
                    all_sources.extend(sources)
                    msgs.append({"role": "tool", "content": result_str})

                if all_sources:
                    unique = list({s["id"]: s for s in all_sources}.values())
                    _src   = [{"num": i + 1, "id": s["id"], "titulo": s["titulo"]}
                              for i, s in enumerate(unique)]
                    await emit("sources", value=_src)

                    numbered_list = "\n".join(f"[{s['num']}] {s['titulo']}" for s in _src)
                    example = _src[0]
                    msgs.append({
                        "role": "system",
                        "content": (
                            f"Recetas disponibles en el libro:\n{numbered_list}\n\n"
                            "Al mencionar cualquier receta usa su número entre corchetes "
                            f"justo después del nombre. Ejemplo: \"{example['titulo']} [{example['num']}]\".\n"
                            "Solo usa estos números. No pongas corchetes en otras cosas."
                        )
                    })

                await emit("thought", value="Preparando la respuesta…")
                async for chunk in llm_stream(msgs, temperature=0.1):
                    if chunk == "\n\n[DONE]":
                        break
                    elif chunk:
                        full_ai += chunk
                        await emit("token", value=chunk)
                await emit("done")

            else:
                # No se usaron herramientas de forma explícita. Ejecutamos RAG de respaldo siempre
                await emit("thought", value="Buscando en el recetario...")
                try:
                    docs = await perform_search(message, 4)
                except Exception:
                    docs = []
                
                if docs:
                    for r in docs:
                        if r.get("_id"):
                            _src.append({"id": r["_id"], "titulo": r["titulo"]})
                    
                    unique = list({s["id"]: s for s in _src}.values())
                    _src   = [{"num": i + 1, "id": s["id"], "titulo": s["titulo"]}
                              for i, s in enumerate(unique)]
                    await emit("sources", value=_src)

                    numbered_list = "\n".join(f"[{s['num']}] {s['titulo']}" for s in _src)
                    example = _src[0]
                    msgs.append({
                        "role": "system",
                        "content": (
                            f"Recetas del libro (CONTEXTO):\n{json.dumps(docs, ensure_ascii=False)}\n\n"
                            f"Recetas disponibles:\n{numbered_list}\n\n"
                            "Al mencionar cualquier receta del libro, usa obligatoriamente su número entre corchetes "
                            f"justo después del nombre. Ejemplo: \"{example['titulo']} [{example['num']}]\".\n"
                            "Solo usa estos números. No pongas corchetes para otras cosas."
                        )
                    })
                    
                    await emit("thought", value="Preparando la respuesta…")
                    async for chunk in llm_stream(msgs, temperature=0.1):
                        if chunk == "\n\n[DONE]":
                            break
                        elif chunk:
                            full_ai += chunk
                            await emit("token", value=chunk)
                    await emit("done")
                else:
                    # RAG vacío, transmitimos el content de la primera llamada directamente
                    await emit("thought", value="Respondiendo...")
                    for chunk in re.split(r"(\s+)", content):
                        if chunk:
                            full_ai += chunk
                            await emit("token", value=chunk)
                            await asyncio.sleep(0.005)
                    await emit("done")

    except Exception as exc:
        await emit("error", value=str(exc))

    finally:
        if full_ai:
            _wh.append({"role": "assistant", "content": full_ai, "sources": _src})

        # ── Generar título asíncronamente en background ───────────────────
        if is_new or old_title in ("", "Nueva conversación"):
            asyncio.create_task(async_update_title(chat_id, message, full_ai, _wh, _db_exists, out))
        else:
            try:
                with _chat_conn() as conn:
                    conn.execute(
                        "UPDATE chats SET history=?, updated_at=? WHERE id=?",
                        (json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                    )
                    conn.commit()
            except Exception:
                pass
            await out.put(None)
            _active.pop(chat_id, None)


@app.post("/api/chat")
async def chat(req: ChatRequest):
    chat_id = req.chat_id or str(uuid.uuid4())

    if chat_id not in _active:
        with _chat_conn() as conn:
            row = conn.execute(
                "SELECT title, history FROM chats WHERE id=?", (chat_id,)
            ).fetchone()
        if row:
            history   = json.loads(row["history"])
            is_new    = False
            old_title = row["title"]
        else:
            history   = []
            is_new    = True
            old_title = ""

        out: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _process_chat(chat_id, req.message, history, is_new, old_title, out)
        )
        _active[chat_id] = (task, out)
    else:
        _, out = _active[chat_id]

    async def stream():
        yield _sse("chat_id", value=chat_id)
        while True:
            try:
                item = await asyncio.wait_for(out.get(), timeout=300.0)
            except asyncio.TimeoutError:
                break
            if item is None:
                break
            yield item

    return StreamingResponse(stream(), media_type="text/event-stream")

# ─── Historial de Chats ───────────────────────────────────────────────

@app.get("/api/chats")
async def list_chats():
    with _chat_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return {"chats": [dict(r) for r in rows]}

@app.post("/api/chats")
async def create_chat(req: ChatSessionCreate):
    chat_id = str(uuid.uuid4())
    with _chat_conn() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, '[]', ?)",
            (chat_id, req.title, int(time.time())),
        )
        conn.commit()
    return {"id": chat_id, "title": req.title}

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    with _chat_conn() as conn:
        row = conn.execute(
            "SELECT history FROM chats WHERE id=?", (chat_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404)
    return {"id": chat_id, "history": json.loads(row["history"])}

@app.put("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, req: UpdateChatTitleRequest):
    with _chat_conn() as conn:
        cur = conn.execute(
            "UPDATE chats SET title=? WHERE id=?",
            (req.title.strip()[:120], chat_id),
        )
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"id": chat_id, "title": req.title.strip()[:120]}

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    with _chat_conn() as conn:
        cur = conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"status": "deleted"}

# ─── Gestión de Recetas ───────────────────────────────────────────────

@app.post("/api/recipes/extract")
async def recipe_extract(req: ExtractRequest):
    async def gen():
        async for chunk in llm_stream([
            {
                "role": "system",
                "content": (
                    "Eres un extractor de datos culinarios. "
                    f"Devuelve SOLO JSON válido con este esquema exacto (sin texto adicional):\n{EXTRACTION_SCHEMA}"
                ),
            },
            {"role": "user", "content": f"Extrae la receta del siguiente texto:\n\n{req.text}"},
        ]):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/api/recipes/save")
async def recipe_save(req: SaveRecipeRequest):
    doc_id = await store_recipe_async(req.recipe)
    return {"id": doc_id}

@app.put("/api/recipes/{recipe_id}")
async def recipe_update(recipe_id: str, req: UpdateRecipeRequest):
    vector = await embed(build_embed_text(req.recipe))
    get_col().update(
        ids=[recipe_id],
        embeddings=[vector],
        documents=[json.dumps(req.recipe, ensure_ascii=False)],
    )
    return {"status": "updated"}

@app.delete("/api/recipes/{recipe_id}")
async def recipe_delete(recipe_id: str):
    data = get_col().get(ids=[recipe_id])
    if not data["ids"]:
        raise HTTPException(404, "Receta no encontrada")
    get_col().delete(ids=[recipe_id])
    return {"status": "deleted"}

@app.post("/api/recipes/refine")
async def recipe_refine(req: RefineRecipeRequest):
    msg = await llm([
        {
            "role": "system",
            "content": (
                "Eres un chef experto. Refina la receta según las instrucciones "
                f"y devuelve SOLO JSON válido con este esquema:\n{EXTRACTION_SCHEMA}"
            ),
        },
        {
            "role": "user",
            "content": f"Receta:\n{json.dumps(req.recipe, ensure_ascii=False)}\n\nInstrucciones: {req.instructions}",
        },
    ])
    return {"recipe": extract_json(msg.get("content", ""))}

# ─── MCP (Model Context Protocol) ─────────────────────────────────────
# Expone herramientas en formato MCP para que clientes externos puedan
# conectar aplicaciones a la IA del recetario.

@app.get("/api/mcp/tools")
async def mcp_list_tools():
    """Lista las herramientas disponibles en formato MCP estándar."""
    return {
        "version": "2024-11-05",
        "description": "Ratatui MCP Server — Acceso al recetario inteligente",
        "tools": [t["function"] for t in MCP_TOOLS],
    }

@app.post("/api/mcp/call")
async def mcp_call_tool(req: MCPCallRequest):
    """Ejecuta una herramienta MCP directamente (para clientes externos)."""
    valid = {t["function"]["name"] for t in MCP_TOOLS}
    if req.tool not in valid:
        raise HTTPException(400, f"Tool '{req.tool}' no existe. Disponibles: {sorted(valid)}")
    result_str, sources = await execute_tool(req.tool, req.params)
    return {"result": json.loads(result_str), "sources": sources}

# ─── RAG Empaquetado ──────────────────────────────────────────────────
# Endpoint RAG puro para integraciones externas (sin personalidad de chef).

@app.post("/api/rag/query")
async def rag_query_endpoint(req: ChatRequest):
    result = await rag.query(req.message)
    return result

# ─── Entrenamiento / Modelfile ────────────────────────────────────────
# Genera un Ollama Modelfile con el system prompt Y pares de entrenamiento
# en formato MESSAGE, demostrando el concepto de fine-tuning local con
# parejas pregunta-respuesta definidas en training_data.json.

@app.get("/api/modelfile")
async def get_modelfile():
    message_block = "\n".join(
        f'MESSAGE user """{p["question"]}"""\nMESSAGE assistant """{p["answer"]}"""'
        for p in TRAINING_PAIRS
    )
    modelfile = f"""FROM {LLM_MODEL}

SYSTEM \"\"\"{SYSTEM_PROMPT}\"\"\"

{message_block}

PARAMETER temperature 0.4
PARAMETER top_p 0.95
PARAMETER num_ctx 4096
"""
    return {
        "modelfile": modelfile,
        "model_name": "ratatui-chef",
        "training_pairs_count": len(TRAINING_PAIRS),
        "instructions": [
            "1. Copia el contenido del campo 'modelfile' en un archivo llamado 'Modelfile'",
            "2. Ejecuta: ollama create ratatui-chef -f Modelfile",
            "3. Prueba el modelo: ollama run ratatui-chef",
            "4. Actualiza LLM_MODEL en main.py a 'ratatui-chef' para usarlo en la app",
        ],
    }


@app.get("/api/training/pairs")
async def training_pairs():
    """Devuelve los pares de entrenamiento cargados desde training_data.json."""
    return {
        "total": len(TRAINING_PAIRS),
        "pairs": TRAINING_PAIRS,
    }


@app.post("/api/training/compare")
async def training_compare(req: TrainingCompareRequest):
    """
    Compara la respuesta del modelo base (sin contexto) vs el modelo entrenado
    (con system prompt de Ratatui + pares de entrenamiento como ejemplos).
    Demuestra el diferencial antes/después del entrenamiento.
    """
    question = req.question.strip()

    # ── ANTES: modelo base sin ningún contexto ────────────────────────
    base_msg = await llm(
        [{"role": "user", "content": question}],
        temperature=0.7,
    )
    base_response = base_msg.get("content", "")

    # ── DESPUÉS: modelo con system prompt + ejemplos de entrenamiento ─
    training_context = "\n\n".join(
        f'Usuario: {p["question"]}\nRatatui: {p["answer"]}'
        for p in TRAINING_PAIRS[:5]
    )
    trained_msg = await llm(
        [
            {
                "role": "system",
                "content": (
                    f"{SYSTEM_PROMPT}\n\n"
                    "## EJEMPLOS DE ENTRENAMIENTO\n"
                    "A continuación tienes ejemplos de cómo debes responder:\n\n"
                    f"{training_context}"
                ),
            },
            {"role": "user", "content": question},
        ],
        temperature=0.4,
    )
    trained_response = trained_msg.get("content", "")

    return {
        "question": question,
        "before": {
            "label": f"Modelo base ({LLM_MODEL}) — sin entrenamiento",
            "response": base_response,
        },
        "after": {
            "label": f"Modelo entrenado (ratatui-chef) — con {len(TRAINING_PAIRS)} pares",
            "response": trained_response,
        },
    }


# ─── Static Files ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/css3d")
async def css3d_page():
    return FileResponse("static/css3d.html")

@app.get("/{full_path:path}")
async def catch_all(_full_path: str = ""):
    return FileResponse("static/index.html")
