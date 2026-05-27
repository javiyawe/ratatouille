"""
Ratatui — Recetario Inteligente con IA Agéntica
Backend FastAPI modularizado con RAG, ChromaDB, Ollama y MCP.

Arranque:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.api.recipes import router as recipes_router
from app.api.chats import router as chats_router
from app.api.training import router as training_router

app = FastAPI(title="Ratatui API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar bases de datos (Chroma y SQLite)
init_db()

# Montar routers
app.include_router(recipes_router)
app.include_router(chats_router)
app.include_router(training_router)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/css3d")
async def css3d_page():
    return FileResponse("static/css3d.html")

@app.get("/")
async def landing():
    return FileResponse("static/landing.html")

@app.get("/recetario")
@app.get("/recetario/{full_path:path}")
async def catch_all(_full_path: str = ""):
    return FileResponse("static/index.html")
