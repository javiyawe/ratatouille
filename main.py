"""
Ratatui — Recetario Inteligente con IA Agéntica
Backend FastAPI con RAG, ChromaDB, Ollama y MCP.

Arranque:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import json
import re
import uuid
import time
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
EMBED_MODEL = "bge-m3:latest"
LLM_MODEL   = "qwen2.5:7b"

app = FastAPI(title="Ratatui API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_chroma = chromadb.PersistentClient(path="./chroma_db")

def get_col():
    return _chroma.get_or_create_collection(
        name="recipes",
        metadata={"hnsw:space": "cosine"},
    )

def get_chat_col():
    return _chroma.get_or_create_collection(
        name="chats",
        metadata={"hnsw:space": "cosine"},
    )

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
                    "n":     {"type": "integer", "description": "Número máximo de resultados (1-5)", "default": 3}
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
        vec = await embed(query)
        res = safe_query(vec, n)
        found = parse_docs(res)
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

SYSTEM_PROMPT = """Eres Ratatui, el legendario 'Petit Chef' de París.
Tu paladar es infalible, tu técnica impecable y tu pasión por la cocina, contagiosa.

═══ FILOSOFÍA CULINARIA ═══
- "Cualquiera puede cocinar, pero solo el intrépido puede ser un gran chef".
- Buscas la perfección en la simplicidad.
- Amas los ingredientes frescos, la técnica francesa clásica y la innovación molecular.

═══ TONO Y ESTILO ═══
- Elegante, apasionado, un poco poético y siempre profesional.
- Usas expresiones francesas con naturalidad: "¡Magnifique!", "C'est une explosion de saveurs", "Mise en place".
- Eres humilde (eres una rata, después de todo) pero extremadamente seguro de tu conocimiento.

═══ ESTRUCTURA DE RESPUESTA OBLIGATORIA (MARKDOWN) ═══
1. **L'Inspiration**: Un breve párrafo introductorio que despierte el apetito.
2. **### 🛒 Mise en Place (Para [X] personas)**
   - Lista clara de ingredientes con cantidades precisas.
3. **### 👨‍🍳 El Proceso Artístico**
   - Pasos numerados con títulos en negrita.
   - Explica el *porqué* de las técnicas importantes.
4. **### 🍷 Le Mariage (Opcional)**
   - Sugiere un vino, una bebida o un acompañamiento.
5. **💡 Le Petit Secret**: Un truco final de chef.

═══ REGLAS DE CONTEXTO ═══
- Si tienes resultados de herramientas (recetas del libro del usuario), úsalos como base sagrada.
- No inventes datos que contradigan el contexto (tiempos, ingredientes).
- Si no encuentras una receta exacta, di que vas a "crear una nueva inspirada en tu estilo".
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

def build_embed_text(r: dict) -> str:
    parts = [r.get("titulo", ""), r.get("descripcion", ""), r.get("tipo_cocina", "")]
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
    vec = await embed(req.query)
    res = safe_query(vec, req.n_results, build_where(req.max_time, req.difficulty))
    return {"recipes": parse_docs(res), "query": req.query}

# ─── Chat con IA Agéntica (tool-calling loop) ─────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    chat_id = req.chat_id or str(uuid.uuid4())
    chat_data = get_chat_col().get(ids=[chat_id])
    history = json.loads(chat_data["documents"][0]) if chat_data["documents"] else []

    async def event_generator():
        yield f"CHAT_ID: {chat_id}\n"

        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-6:]:
            msgs.append(h)
        msgs.append({"role": "user", "content": req.message})

        all_sources = []

        # Loop agéntico: el LLM decide qué herramientas usar (máx. 3 rondas)
        for _ in range(3):
            agent_msg = await llm(msgs, temperature=0.3, tools=MCP_TOOLS)
            tool_calls = agent_msg.get("tool_calls") or []

            if not tool_calls:
                break  # No más herramientas — listo para responder

            # Registrar la llamada del agente en el historial de mensajes
            msgs.append({
                "role": "assistant",
                "content": agent_msg.get("content") or "",
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                func       = tc.get("function", {})
                tool_name  = func.get("name", "")
                raw_args   = func.get("arguments", {})
                tool_params = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")

                label = tool_name.replace("_", " ").capitalize()
                yield f"THOUGHT: {label}...\n"

                result_str, sources = await execute_tool(tool_name, tool_params)
                all_sources.extend(sources)

                msgs.append({"role": "tool", "content": result_str})

        # Emitir fuentes únicas al frontend
        if all_sources:
            unique_sources = list({s["id"]: s for s in all_sources}.values())
            yield f"SOURCES: {json.dumps(unique_sources, ensure_ascii=False)}\n"

        yield "THOUGHT: Preparando mi respuesta...\n"

        # Respuesta final en streaming
        full_ai = ""
        async for chunk in llm_stream(msgs, temperature=0.4):
            if chunk and chunk != "\n\n[DONE]":
                full_ai += chunk
            yield chunk

        # Persistir historial
        history.append({"role": "user",      "content": req.message})
        history.append({"role": "assistant", "content": full_ai})
        meta = {"title": req.message[:40], "updated_at": int(time.time())}
        if not chat_data["ids"]:
            get_chat_col().add(
                ids=[chat_id],
                documents=[json.dumps(history, ensure_ascii=False)],
                metadatas=[meta],
            )
        else:
            get_chat_col().update(
                ids=[chat_id],
                documents=[json.dumps(history, ensure_ascii=False)],
                metadatas=[meta],
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# ─── Historial de Chats ───────────────────────────────────────────────

@app.get("/api/chats")
async def list_chats():
    data = get_chat_col().get(include=["metadatas"])
    chats = [
        {
            "id": cid,
            "title": data["metadatas"][i].get("title", "Chat"),
            "updated_at": data["metadatas"][i].get("updated_at", 0),
        }
        for i, cid in enumerate(data["ids"])
    ]
    chats.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"chats": chats}

@app.post("/api/chats")
async def create_chat(req: ChatSessionCreate):
    chat_id = str(uuid.uuid4())
    get_chat_col().add(
        ids=[chat_id],
        documents=[json.dumps([], ensure_ascii=False)],
        metadatas=[{"title": req.title, "updated_at": int(time.time())}],
    )
    return {"id": chat_id, "title": req.title}

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    data = get_chat_col().get(ids=[chat_id])
    if not data["ids"]:
        raise HTTPException(404)
    return {"id": chat_id, "history": json.loads(data["documents"][0])}

@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    data = get_chat_col().get(ids=[chat_id])
    if not data["ids"]:
        raise HTTPException(404)
    get_chat_col().delete(ids=[chat_id])
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
# Genera un Ollama Modelfile para "entrenar" (personalizar) el modelo
# con el system prompt de Ratatui — concepto de fine-tuning local.

@app.get("/api/modelfile")
async def get_modelfile():
    modelfile = f"""FROM {LLM_MODEL}

SYSTEM \"\"\"{SYSTEM_PROMPT}\"\"\"

PARAMETER temperature 0.4
PARAMETER top_p 0.95
PARAMETER num_ctx 4096
"""
    return {
        "modelfile": modelfile,
        "model_name": "ratatui-chef",
        "instructions": [
            "1. Copia el contenido del campo 'modelfile' en un archivo llamado 'Modelfile'",
            "2. Ejecuta: ollama create ratatui-chef -f Modelfile",
            "3. Prueba el modelo: ollama run ratatui-chef",
            "4. Actualiza LLM_MODEL en main.py a 'ratatui-chef' para usarlo en la app",
        ],
    }

# ─── Static Files ─────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/{full_path:path}")
async def catch_all(_full_path: str = ""):
    return FileResponse("static/index.html")
