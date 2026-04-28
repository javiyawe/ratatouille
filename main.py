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
    max_time: Optional[int] = None      # minutos
    difficulty: Optional[str] = None   # Fácil | Media | Difícil


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

# ─────────────────────────── Nivel 3: System Prompt RAG ──────────────
# Ingeniería de prompt con Chain-of-Thought obligatorio para cálculos
# y Alquimia Gastronómica para el Nivel 4.

SYSTEM_PROMPT = """Eres Ratatui, el pequeño gran Chef.
Eres un genio culinario con un olfato prodigioso y una pasión inmensa por la cocina francesa y mediterránea.

═══ DIRECTIVAS DE PERSONALIDAD ═══
1. Habla con humildad pero con la pasión de un verdadero artista. Eres una rata, sí, pero con el paladar más refinado de todo París.
2. Usas términos como "¡Magnifique!", "C'est la vie", "Pasión por el detalle", "Tout est possible".
3. Tu filosofía: "Cualquiera puede cocinar, pero solo el intrépido puede ser un gran chef".

═══ FORMATO DE RESPUESTA OBLIGATORIO ═══
Tus respuestas deben seguir SIEMPRE esta estructura para que sean legibles y bellas:

1. INTRO: Un saludo breve y cálido explicando qué has adaptado o por qué sugieres esta receta.
2. ### 🛒 Ingredientes (Para [X] personas)
   - Lista con bullet points.
   - Cantidad y nombre del ingrediente claros.
3. ### 👨‍🍳 Preparación
   1. Pasos numerados.
   2. Usa negritas para acciones clave (ej: **Saltear**, **Hornear**).
4. CONSEJO DEL CHEF: Un pequeño párrafo final con un truco de experto ("Un pequeño secreto...").

═══ MODO ALQUIMIA ═══
Solo si el usuario pide explícitamente "fusionar", "inventar" o "mezcla", activa tu creatividad molecular.
"""


def is_alchemy(message: str) -> bool:
    keywords = [
        "fusionar", "fusión", "fusion", "inventar", "cruzar",
        "alquimia", "crear nuevo", "plato nuevo", "inédito",
        "experimenta", "combina recetas", "mezcla recetas",
        "invéntame", "crea un plato", "receta nueva",
    ]
    m = message.lower()
    return any(kw in m for kw in keywords)


def safe_query(query_embedding: list, n: int, where: Optional[dict] = None) -> dict:
    """Consulta ChromaDB manejando colección vacía."""
    total = get_col().count()
    if total == 0:
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    n = min(n, total)
    kwargs: dict = {
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
    """Normaliza campos de la receta para asegurar compatibilidad con la UI."""
    # Mapear título con fallback extremo
    if not r.get("titulo"):
        r["titulo"] = r.get("nombre") or r.get("receta") or r.get("title") or r.get("plato")
    
    if not r.get("titulo") or str(r.get("titulo")).lower() == "null":
        desc = r.get("descripcion") or ""
        r["titulo"] = desc[:30] + "..." if desc else "Receta sin nombre"

    # Mapear ingredientes
    if not r.get("ingredientes"):
        r["ingredientes"] = r.get("otros_ingredientes") or r.get("items") or []
    
    # Asegurar estructura de ingredientes
    if isinstance(r.get("ingredientes"), list):
        normalized_ings = []
        for ing in r["ingredientes"]:
            if isinstance(ing, str):
                normalized_ings.append({"nombre": ing, "cantidad": "", "unidad": ""})
            elif isinstance(ing, dict):
                nombre = ing.get("nombre") or ing.get("item") or ing.get("ingrediente") or "Ingrediente"
                
                # Limpieza de nulos y strings raros
                cant = str(ing.get("cantidad") or "").strip()
                if cant.lower() == "null": cant = ""
                
                unit = str(ing.get("unidad") or "").strip()
                if unit.lower() == "null": unit = ""
                
                # Evitar unidades duplicadas (ej: "500g" y "g")
                # Si la unidad ya está al final de la cantidad, la quitamos de la cantidad para normalizar
                if unit and cant.lower().endswith(unit.lower()):
                    cant = cant[: -len(unit)].strip()
                
                normalized_ings.append({"nombre": nombre, "cantidad": cant, "unidad": unit})
        r["ingredientes"] = normalized_ings
    else:
        r["ingredientes"] = []

    # Mapear pasos
    if not r.get("pasos"):
        r["pasos"] = r.get("preparacion") or r.get("procesos") or r.get("elaboracion") or []
    if isinstance(r["pasos"], str):
        r["pasos"] = [r["pasos"]]
    elif not isinstance(r["pasos"], list):
        r["pasos"] = []

    return r


def parse_docs(results: dict) -> list[dict]:
    recipes = []
    for i, doc in enumerate(results["documents"][0]):
        try:
            r = json.loads(doc)
            r = normalize_recipe(r)
            r["_id"] = results["ids"][0][i]
            if results.get("distances") and results["distances"][0]:
                r["_relevance"] = round(1 - results["distances"][0][i], 3)
            recipes.append(r)
        except Exception:
            pass
    return recipes

# ─────────────────────── Extracción de recetas vía LLM ───────────────
# Usado tanto por los endpoints de ingesta web como por ingest.py.

EXTRACTION_SYSTEM = """Eres un extractor de datos ultrarrápido.
Devuelve SOLO JSON puro. Sin markdown, sin bloques ```json.

ESQUEMA:
{
  "titulo": "string",
  "descripcion": "string",
  "tipo_cocina": "string",
  "dificultad": "Fácil/Media/Difícil",
  "porciones": 0,
  "tiempos": {"total_minutos": 0},
  "ingredientes": [{"nombre": "string", "cantidad": "string", "unidad": "string"}],
  "pasos": ["paso 1", "paso 2"]
}
"""


async def extract_recipe_llm(raw_text: str) -> dict:
    """Extrae estructura JSON de texto libre usando qwen2.5:7b."""
    content = await llm(
        [
            {"role": "system", "content": EXTRACTION_SYSTEM},
            {"role": "user", "content": f"Extrae y estructura esta receta:\n\n{raw_text}"},
        ],
        temperature=0.05,
    )
    content = re.sub(r"```(?:json)?\s*", "", content).strip()
    content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE).strip()
    match = re.search(r"\{[\s\S]+\}", content)
    if match:
        content = match.group(0)
    return json.loads(content)


def build_embed_text(r: dict) -> str:
    parts = [
        r.get("titulo") or "",
        r.get("descripcion") or "",
        r.get("tipo_cocina") or "",
        r.get("tecnica_coccion") or "",
        " ".join(r.get("etiquetas") or []),
        r.get("notas_quimicas") or "",
        " ".join(i.get("nombre", "") for i in (r.get("ingredientes") or [])),
        " ".join((r.get("pasos") or [])[:4]),
    ]
    return " | ".join(p for p in parts if p.strip())


def store_recipe(recipe: dict) -> str:
    """Embeds y guarda una receta ya estructurada. Devuelve el ID generado."""
    # Embedding síncrono no disponible aquí; el caller debe pasar el vector.
    # Esta función NO genera el embedding — usa store_recipe_with_embed.
    raise NotImplementedError("Usa store_recipe_async desde un endpoint async.")


async def store_recipe_async(recipe: dict) -> str:
    tiempos = recipe.get("tiempos") or {}
    metadata = {
        "titulo":             str(recipe.get("titulo") or "Sin título"),
        "dificultad":         str(recipe.get("dificultad") or "Media"),
        "tipo_cocina":        str(recipe.get("tipo_cocina") or ""),
        "tecnica_coccion":    str(recipe.get("tecnica_coccion") or ""),
        "etiquetas":          json.dumps(recipe.get("etiquetas") or [], ensure_ascii=False),
        "total_time_minutes": int(tiempos.get("total_minutos") or 0),
        "porciones":          int(recipe.get("porciones") or 0),
        "archivo_origen":     str(recipe.get("archivo_origen") or "web_ui"),
    }
    doc_id = str(uuid.uuid4())
    vector = await embed(build_embed_text(recipe))
    get_col().add(
        ids=[doc_id],
        embeddings=[vector],
        documents=[json.dumps(recipe, ensure_ascii=False)],
        metadatas=[metadata],
    )
    return doc_id

# ─────────────────────── Modelos de ingesta web ───────────────────────

class ExtractRequest(BaseModel):
    text: str

class SaveRecipeRequest(BaseModel):
    recipe: dict  # JSON ya estructurado devuelto por /api/recipes/extract

# ─────────────────────────── Endpoints ───────────────────────────────

@app.get("/api/stats")
async def stats():
    return {"total_recipes": get_col().count()}


@app.get("/api/recipes")
async def get_recipes(limit: int = 50):
    if get_col().count() == 0:
        return {"recipes": []}
    raw = get_col().get(
        limit=limit,
        include=["documents", "metadatas"],
    )
    recipes = []
    for i, doc in enumerate(raw["documents"]):
        try:
            r = json.loads(doc)
            r = normalize_recipe(r)
            r["_id"] = raw["ids"][i]
            recipes.append(r)
        except Exception:
            pass
    return {"recipes": recipes}


@app.post("/api/search")
async def search(req: SearchRequest):
    """
    Nivel 1: búsqueda semántica NLP.
    Vectoriza la query con bge-m3, busca en ChromaDB con filtros opcionales.
    """
    if get_col().count() == 0:
        return {"recipes": [], "query": req.query}

    vec = await embed(req.query)
    where = build_where(req.max_time, req.difficulty)
    results = safe_query(vec, req.n_results, where)
    recipes = parse_docs(results)
    return {"recipes": recipes, "query": req.query}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Niveles 3 y 4: RAG con Chain-of-Thought matemático + Alquimia Gastronómica (Streaming).
    """
    from fastapi.responses import StreamingResponse
    
    alchemy_mode = is_alchemy(req.message)
    n_ctx = 6 if alchemy_mode else 4

    vec = await embed(req.message)
    results = safe_query(vec, n_ctx)
    context_recipes = parse_docs(results)

    # ── Construir contexto para el prompt ──────────────────────────────
    if not context_recipes:
        context_block = ("No hay recetas en la base de datos todavía.")
    else:
        parts = []
        for r in context_recipes:
            parts.append(f"── {r.get('titulo','Receta')} ──\n"
                         + json.dumps(r, ensure_ascii=False, indent=2))
        context_block = "\n\n".join(parts)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in req.history[-10:]:
        messages.append(msg)

    user_content = (
        f"CONTEXTO DEL RECETARIO:\n```json\n{context_block}\n```\n\n"
        f"PREGUNTA: {req.message}"
    )
    messages.append({"role": "user", "content": user_content})

    temperature = 0.85 if alchemy_mode else 0.4
    
    async def event_generator():
        # Enviar fuentes primero
        sources = [r.get("titulo") for r in context_recipes[:3]]
        yield f"SOURCES: {json.dumps(sources, ensure_ascii=False)}\n"
        
        async for chunk in llm_stream(messages, temperature=temperature):
            yield chunk

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/recipes/extract")
async def recipe_extract(req: ExtractRequest):
    """
    Paso 1 de la ingesta web: toma texto bruto y streamea la estructura JSON.
    """
    from fastapi.responses import StreamingResponse
    
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM},
        {"role": "user", "content": f"Extrae esta receta:\n\n{req.text}"}
    ]

    async def event_generator():
        print(f"DEBUG: Iniciando extracción para: {req.text[:50]}...")
        try:
            async for chunk in llm_stream(messages, temperature=0.1):
                if chunk:
                    yield chunk
        except Exception as e:
            print(f"DEBUG ERROR: {e}")
            yield f"ERROR: {e}"

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/recipes/save")
async def recipe_save(req: SaveRecipeRequest):
    """
    Paso 2 de la ingesta web: recibe el JSON ya revisado por el usuario,
    genera el embedding con bge-m3 y lo persiste en ChromaDB.
    """
    recipe = req.recipe
    if not recipe:
        raise HTTPException(400, "No se proporcionó ninguna receta.")
    try:
        doc_id = await store_recipe_async(recipe)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Error al conectar con Ollama: {e}")
    recipe["_id"] = doc_id
    return {"id": doc_id, "recipe": recipe}


@app.delete("/api/recipes/{recipe_id}")
async def recipe_delete(recipe_id: str):
    """Elimina una receta de ChromaDB por su ID."""
    try:
        get_col().delete(ids=[recipe_id])
    except Exception as e:
        raise HTTPException(404, f"No se pudo eliminar: {e}")
    return {"deleted": recipe_id}

# ─────────────────────────── Estáticos ───────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{full_path:path}")
async def catch_all(full_path: str):  # noqa: ARG001
    return FileResponse("static/index.html")
