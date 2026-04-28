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

app = FastAPI(title="Ratatouille API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ChromaDB persistente
_chroma = chromadb.PersistentClient(path="./chroma_db")
collection = _chroma.get_or_create_collection(
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

SYSTEM_PROMPT = """Eres Chef IA, asistente culinario científico integrado en un libro de recetas local.

═══ DIRECTIVAS CORE ═══

1. IDIOMA: Responde siempre en el mismo idioma que el usuario.
2. FIDELIDAD A LOS DATOS: Cuando se te proporcione contexto de recetas (JSON estructurado),
   basa tu respuesta EXCLUSIVAMENTE en esos datos. Jamás inventes cantidades, tiempos ni
   ingredientes que no aparezcan en el JSON. Cita siempre: "Según la receta [Título]...".
3. PRECISIÓN MATEMÁTICA para adaptación de raciones o tiempos:
   Usa obligatoriamente este razonamiento Chain-of-Thought visible al usuario:

   Paso 1 → Ración base del JSON: X porciones
   Paso 2 → Ración objetivo: Y porciones
   Paso 3 → Factor de escala: F = Y / X = [valor exacto]
   Paso 4 → Aplicar F a cada ingrediente:
             [ingrediente]: [cantidad_base] × F = [resultado con unidad]
   Paso 5 → Ajustar tiempos (NOTA: el horneado NO es lineal; usa la regla
             t_nuevo = t_base × F^(2/3) para masas; los salteados sí escalan linealmente)
   Paso 6 → Resultado final resumido

4. FORMATO: Usa Markdown. Ingredientes en bullets con cantidades. Pasos numerados.

═══ MODO ALQUIMIA GASTRONÓMICA (Nivel 4) ═══

Se activa cuando el usuario usa: "fusionar", "inventar", "cruzar", "alquimia",
"crear nuevo plato", "experimenta", "combina recetas".

Al activarse, actúas como ALQUIMISTA CULINARIO CIENTÍFICO:
  ▸ Tomas la TÉCNICA DE COCCIÓN principal de la Receta A (la primera del contexto)
  ▸ Tomas los INGREDIENTES ESTRUCTURALES de la Receta B (la segunda del contexto)
  ▸ Justificas el maridaje usando principios termodinámicos y química culinaria:
      — Reacción de Maillard (caramelización de aminoácidos + azúcares, T > 140°C)
      — Gelificación (ruptura de colágeno en gelatina, T 70-80°C)
      — Emulsificación (lecitinas, proteínas como agentes tensoactivos)
      — Contraste osmótico (sal/azúcar en marinados)
  ▸ Nombras el plato con un nombre poético-científico (e.g. "Coalescencia Termal de...")
  ▸ Generas la receta completa del plato inédito
  ▸ Explicas por qué funciona a nivel molecular, de textura y de sabor
  ▸ Nunca produces un resultado que ya exista en la base de datos

Estructura de respuesta en modo alquimia:
  ⚗️ NOMBRE DEL PLATO INÉDITO
  📐 BASE CIENTÍFICA DE LA FUSIÓN (2-3 párrafos)
  🧪 INGREDIENTES (de ambas recetas, reinterpretados)
  📋 PROCESO (pasos numerados con técnicas de la Receta A)
  🔬 NOTAS DE ALQUIMIA (reacciones esperadas, texturas, temperatura crítica)
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
    total = collection.count()
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
    return collection.query(**kwargs)


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


def parse_docs(results: dict) -> list[dict]:
    recipes = []
    for i, doc in enumerate(results["documents"][0]):
        try:
            r = json.loads(doc)
            r["_id"] = results["ids"][0][i]
            if results.get("distances") and results["distances"][0]:
                r["_relevance"] = round(1 - results["distances"][0][i], 3)
            recipes.append(r)
        except Exception:
            pass
    return recipes

# ─────────────────────── Extracción de recetas vía LLM ───────────────
# Usado tanto por los endpoints de ingesta web como por ingest.py.

EXTRACTION_SYSTEM = """Eres un extractor de datos culinarios de precisión quirúrgica.
Tu ÚNICA tarea: analizar texto de receta en cualquier formato o idioma y devolver un JSON válido.

REGLAS ABSOLUTAS:
- Devuelve ÚNICAMENTE el JSON. Cero texto adicional, cero markdown, cero explicaciones.
- Si un campo no existe en el texto, usa null o [] según corresponda.
- Las cantidades deben ser strings numéricos o fraccionarios ("200", "1/2", "al gusto").
- El JSON debe ser válido y parseable con json.loads(). Solo comillas dobles.

ESQUEMA OBLIGATORIO:
{
  "titulo": "string",
  "descripcion": "string, máximo 2 oraciones",
  "porciones": 4,
  "ingredientes": [
    {
      "nombre": "string",
      "cantidad": "string",
      "unidad": "string (g|ml|taza|cucharada|cucharadita|unidad|diente|manojo|al gusto)",
      "preparacion": "string opcional"
    }
  ],
  "pasos": ["paso 1", "paso 2"],
  "tiempos": {
    "preparacion_minutos": 15,
    "coccion_minutos": 30,
    "reposo_minutos": 0,
    "total_minutos": 45
  },
  "etiquetas": ["tag1", "tag2"],
  "dificultad": "Fácil",
  "tipo_cocina": "string",
  "tecnica_coccion": "string",
  "notas_quimicas": "string con reacciones relevantes: Maillard, gelificación, emulsificación, etc.",
  "valor_nutricional": {
    "calorias_por_porcion": 350,
    "proteinas_g": 25,
    "carbohidratos_g": 40,
    "grasas_g": 12
  }
}

dificultad debe ser exactamente uno de: "Fácil", "Media", "Difícil"
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
    collection.add(
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
    return {"total_recipes": collection.count()}


@app.get("/api/recipes")
async def get_recipes(limit: int = 50):
    if collection.count() == 0:
        return {"recipes": []}
    raw = collection.get(
        limit=limit,
        include=["documents", "metadatas"],
    )
    recipes = []
    for i, doc in enumerate(raw["documents"]):
        try:
            r = json.loads(doc)
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
    if collection.count() == 0:
        return {"recipes": [], "query": req.query}

    vec = await embed(req.query)
    where = build_where(req.max_time, req.difficulty)
    results = safe_query(vec, req.n_results, where)
    recipes = parse_docs(results)
    return {"recipes": recipes, "query": req.query}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    Niveles 3 y 4: RAG con Chain-of-Thought matemático + Alquimia Gastronómica.
    """
    alchemy_mode = is_alchemy(req.message)
    n_ctx = 6 if alchemy_mode else 4

    vec = await embed(req.message)
    results = safe_query(vec, n_ctx)
    context_recipes = parse_docs(results)

    # ── Construir contexto para el prompt ──────────────────────────────
    if not context_recipes:
        context_block = ("No hay recetas en la base de datos todavía. "
                         "Dile al usuario que pulse el botón ＋ Añadir receta "
                         "en la pestaña Recetario para añadir la primera.")
    elif alchemy_mode and len(context_recipes) >= 2:
        # Nivel 4: elige recetas de extremos del ranking (clusters dispares)
        recipe_a = context_recipes[0]
        recipe_b = context_recipes[-1]
        context_block = (
            "══ RECETA A (TÉCNICA) ══\n"
            + json.dumps(recipe_a, ensure_ascii=False, indent=2)
            + "\n\n══ RECETA B (INGREDIENTES ESTRUCTURALES) ══\n"
            + json.dumps(recipe_b, ensure_ascii=False, indent=2)
        )
    else:
        parts = []
        for r in context_recipes:
            parts.append(f"── {r.get('titulo','Receta')} ──\n"
                         + json.dumps(r, ensure_ascii=False, indent=2))
        context_block = "\n\n".join(parts)

    # ── Construir mensajes ─────────────────────────────────────────────
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Historial reciente (máximo 10 turnos)
    for msg in req.history[-20:]:
        messages.append(msg)

    user_content = (
        f"CONTEXTO DEL RECETARIO (JSON exacto, úsalo como única fuente de verdad):\n"
        f"```json\n{context_block}\n```\n\n"
        f"PREGUNTA: {req.message}"
    )
    if alchemy_mode:
        user_content = (
            "⚗️ MODO ALQUIMIA GASTRONÓMICA ACTIVADO ⚗️\n\n"
            + user_content
            + "\n\nInstrucción: aplica el protocolo de Alquimia Gastronómica completo."
        )

    messages.append({"role": "user", "content": user_content})

    temperature = 0.85 if alchemy_mode else 0.4
    response_text = await llm(messages, temperature=temperature)

    return {
        "response": response_text,
        "alchemy_mode": alchemy_mode,
        "sources": [r.get("titulo", "N/A") for r in context_recipes[:3]],
        "context_count": len(context_recipes),
    }

@app.post("/api/recipes/extract")
async def recipe_extract(req: ExtractRequest):
    """
    Paso 1 de la ingesta web: interpreta texto libre con qwen2.5:7b y devuelve
    el JSON estructurado. NO escribe en ChromaDB — solo extrae para previsualizar.
    """
    if not req.text.strip():
        raise HTTPException(400, "El texto está vacío.")
    try:
        recipe = await extract_recipe_llm(req.text)
    except json.JSONDecodeError as e:
        raise HTTPException(422, f"La IA devolvió JSON inválido: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Error al conectar con Ollama: {e}")
    return {"recipe": recipe}


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
        collection.delete(ids=[recipe_id])
    except Exception as e:
        raise HTTPException(404, f"No se pudo eliminar: {e}")
    return {"deleted": recipe_id}

# ─────────────────────────── Estáticos ───────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/{full_path:path}")
async def catch_all(full_path: str):  # noqa: ARG001
    return FileResponse("static/index.html")
