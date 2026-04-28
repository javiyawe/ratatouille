"""
Ratatouille — Libro de Recetas Inteligente
Backend FastAPI con RAG sobre ChromaDB y Ollama local.

Arranque:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Requisitos previos:
    ollama pull qwen2.5:7b
    ollama pull bge-m3:latest
    pip install -r requirements.txt
"""

import json
import re
import uuid
import time
from typing import Optional, List

import httpx
import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ─────────────────────────── Configuración ────────────────────────────

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3:latest"
LLM_MODEL   = "qwen2.5:7b"

app = FastAPI(title="Ratatui API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ChromaDB persistente
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
    """Vectoriza texto con bge-m3 vía Ollama."""
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        return r.json()["embedding"]


async def llm(messages: list[dict], temperature: float = 0.7) -> str:
    """Llama al LLM qwen2.5:7b vía Ollama (sin stream)."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature, "top_p": 0.95},
            },
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


async def llm_stream(messages: list[dict], temperature: float = 0.7):
    """Generador para streaming desde Ollama."""
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

# ─────────────────────────── System Prompt ───────────────────────────

SYSTEM_PROMPT = """Eres Ratatui, el legendario 'Petit Chef' de París.
Tu paladar es infalible, tu técnica impecable y tu pasión por la cocina, contagiosa.

═══ FILOSOFÍA CULINARIA ═══
- "Cualquiera puede cocinar, pero solo el intrépido puede ser un gran chef".
- Buscas la perfección en la simplicidad.
- Amas los ingredientes frescos, la técnica francesa clásica y la innovación molecular.

═══ TONO Y ESTILO ═══
- Elegante, apasionado, un poco poético y siempre profesional.
- Usas expresiones francesas con naturalidad: "¡Magnifique!", "C'est une explosion de saveurs", "Mise en place", "Le secret está en la reducción".
- Eres humilde (eres una rata, después de todo) pero extremadamente seguro de tu conocimiento.

═══ ESTRUCTURA DE RESPUESTA OBLIGATORIA (MARKDOWN) ═══
Tus respuestas deben ser visualmente impresionantes:

1. **L'Inspiration**: Un breve párrafo introductorio que despierte el apetito.
2. **### 🛒 Mise en Place (Para [X] personas)**
   - Lista clara de ingredientes con cantidades precisas.
   - Si detectas que falta algo clave, sugiérelo.
3. **### 👨‍🍳 El Proceso Artístico**
   - Pasos numerados con títulos en negrita (ej: 1. **La Reducción**: ...).
   - Explica el *porqué* de las técnicas importantes.
4. **### 🍷 Le Mariage (Opcional)**
   - Sugiere un vino, una bebida o un acompañamiento.
5. **💡 Le Petit Secret**: Un truco final de chef para elevar el plato al Nivel 5.

═══ REGLAS DE CONTEXTO ═══
- Si el usuario tiene recetas en su libro (CONTEXTO), úsalas como base sagrada.
- No inventes datos que contradigan el contexto (tiempos, ingredientes).
- Si no encuentras una receta exacta, di que vas a "crear una nueva inspirada en tu estilo".
"""

# ─────────────────────────── Utilidades ───────────────────────────────

def safe_query(query_embedding: list, n: int, where: Optional[dict] = None) -> dict:
    total = get_col().count()
    if total == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    n = min(n, total)
    kwargs = {"query_embeddings": [query_embedding], "n_results": n, "include": ["documents", "metadatas", "distances"]}
    if where: kwargs["where"] = where
    return get_col().query(**kwargs)

def build_where(max_time: Optional[int], difficulty: Optional[str]) -> Optional[dict]:
    conditions = []
    if max_time: conditions.append({"total_time_minutes": {"$lte": max_time}})
    if difficulty: conditions.append({"dificultad": {"$eq": difficulty}})
    if not conditions: return None
    if len(conditions) == 1: return conditions[0]
    return {"$and": conditions}

def normalize_recipe(r: dict) -> dict:
    if not r.get("titulo"):
        r["titulo"] = r.get("nombre") or r.get("receta") or r.get("title") or r.get("plato") or "Receta sin nombre"
    if not r.get("ingredientes"): r["ingredientes"] = []
    if not r.get("pasos"): r["pasos"] = []
    return r

def parse_docs(results: dict) -> list[dict]:
    recipes = []
    if not results or not results.get("documents"): return []
    for i, doc in enumerate(results["documents"][0]):
        try:
            r = json.loads(doc)
            r = normalize_recipe(r)
            r["_id"] = results["ids"][0][i]
            recipes.append(r)
        except: pass
    return recipes

def build_embed_text(r: dict) -> str:
    parts = [r.get("titulo", ""), r.get("descripcion", ""), r.get("tipo_cocina", "")]
    return " | ".join(p for p in parts if p)

async def store_recipe_async(recipe: dict) -> str:
    doc_id = str(uuid.uuid4())
    vector = await embed(build_embed_text(recipe))
    tiempos = recipe.get("tiempos") or {}
    metadata = {
        "titulo": str(recipe.get("titulo", "Sin título")),
        "total_time_minutes": int(tiempos.get("total_minutos", 0)),
        "dificultad": str(recipe.get("dificultad", "Media"))
    }
    get_col().add(ids=[doc_id], embeddings=[vector], documents=[json.dumps(recipe, ensure_ascii=False)], metadatas=[metadata])
    return doc_id

EXTRACTION_SYSTEM = """Eres un extractor de datos culinarios. Devuelve SOLO JSON puro."""

# ─────────────────────────── Endpoints ───────────────────────────────

@app.get("/api/stats")
async def stats():
    return {"total_recipes": get_col().count()}

@app.get("/api/recipes")
async def get_recipes(limit: int = 50):
    if get_col().count() == 0: return {"recipes": []}
    raw = get_col().get(limit=limit, include=["documents", "metadatas"])
    recipes = []
    for i, doc in enumerate(raw["documents"]):
        try:
            r = json.loads(doc)
            r["_id"] = raw["ids"][i]
            recipes.append(normalize_recipe(r))
        except: pass
    return {"recipes": recipes}

@app.post("/api/search")
async def search(req: SearchRequest):
    vec = await embed(req.query)
    res = safe_query(vec, req.n_results, build_where(req.max_time, req.difficulty))
    return {"recipes": parse_docs(res), "query": req.query}

@app.post("/api/chat")
async def chat(req: ChatRequest):
    from fastapi.responses import StreamingResponse
    chat_id = req.chat_id or str(uuid.uuid4())
    chat_data = get_chat_col().get(ids=[chat_id])
    history = json.loads(chat_data["documents"][0]) if chat_data["documents"] else []

    async def event_generator():
        yield f"CHAT_ID: {chat_id}\n"
        
        # 1. Intención
        thought = await llm([{"role": "user", "content": f"Analiza: '{req.message}'. Dime qué harás como Chef Ratatui en 10 palabras."}], temperature=0.5)
        yield f"THOUGHT: {thought.strip()}\n"

        # 2. Búsqueda
        search_trigger = await llm([{"role": "user", "content": f"¿Necesito buscar recetas para: '{req.message}'? Responde SI o NO."}], temperature=0.0)
        context = ""
        if "SI" in search_trigger.upper():
            vec = await embed(req.message)
            res = safe_query(vec, 3)
            found = parse_docs(res)
            if found:
                context = json.dumps(found, ensure_ascii=False)
                refs = [{"id": r["_id"], "titulo": r["titulo"]} for r in found]
                yield f"SOURCES: {json.dumps(refs, ensure_ascii=False)}\n"

        # 3. Generación
        msgs = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\nCONTEXTO:\n{context}"}]
        for h in history[-6:]: msgs.append(h)
        msgs.append({"role": "user", "content": req.message})

        full_ai = ""
        async for chunk in llm_stream(msgs, temperature=0.4):
            if chunk and chunk != "\n\n[DONE]": full_ai += chunk
            yield chunk

        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": full_ai})
        meta = {"title": req.message[:30], "updated_at": int(time.time())}
        if not chat_data["ids"]: get_chat_col().add(ids=[chat_id], documents=[json.dumps(history, ensure_ascii=False)], metadatas=[meta])
        else: get_chat_col().update(ids=[chat_id], documents=[json.dumps(history, ensure_ascii=False)], metadatas=[meta])

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/chats")
async def list_chats():
    data = get_chat_col().get(include=["metadatas"])
    chats = [{"id": cid, "title": data["metadatas"][i].get("title", "Chat"), "updated_at": data["metadatas"][i].get("updated_at", 0)} for i, cid in enumerate(data["ids"])]
    chats.sort(key=lambda x: x["updated_at"], reverse=True)
    return {"chats": chats}

@app.post("/api/chats")
async def create_chat(req: ChatSessionCreate):
    chat_id = str(uuid.uuid4())
    get_chat_col().add(ids=[chat_id], documents=[json.dumps([], ensure_ascii=False)], metadatas=[{"title": req.title, "updated_at": int(time.time())}])
    return {"id": chat_id, "title": req.title}

@app.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    data = get_chat_col().get(ids=[chat_id])
    if not data["ids"]: raise HTTPException(404)
    return {"id": chat_id, "history": json.loads(data["documents"][0])}

@app.post("/api/recipes/extract")
async def recipe_extract(req: ExtractRequest):
    from fastapi.responses import StreamingResponse
    async def gen():
        async for chunk in llm_stream([{"role": "system", "content": "Extract recipe as JSON"}, {"role": "user", "content": req.text}]):
            yield chunk
    return StreamingResponse(gen(), media_type="text/event-stream")

@app.post("/api/recipes/save")
async def recipe_save(req: SaveRecipeRequest):
    doc_id = await store_recipe_async(req.recipe)
    return {"id": doc_id}

@app.put("/api/recipes/{recipe_id}")
async def recipe_update(recipe_id: str, req: UpdateRecipeRequest):
    vector = await embed(build_embed_text(req.recipe))
    get_col().update(ids=[recipe_id], embeddings=[vector], documents=[json.dumps(req.recipe, ensure_ascii=False)])
    return {"status": "updated"}

@app.post("/api/recipes/refine")
async def recipe_refine(req: RefineRecipeRequest):
    res = await llm([{"role": "system", "content": "Refine recipe as JSON"}, {"role": "user", "content": f"Recipe: {json.dumps(req.recipe)}\nInstr: {req.instructions}"}])
    return {"recipe": json.loads(re.search(r"\{.*\}", res, re.DOTALL).group(0))}

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    return FileResponse("static/index.html")
