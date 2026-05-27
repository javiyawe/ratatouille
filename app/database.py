import sqlite3
from pathlib import Path
import chromadb
from app.config import EMBED_MODEL

# ─────────────────────────── ChromaDB ──────────────────────────────
_chroma = chromadb.PersistentClient(path="./chroma_db")

def get_col():
    try:
        col = _chroma.get_collection(name="recipes")
        dim = 768 if EMBED_MODEL == "nomic-embed-text:latest" else 1024
        if col.count() > 0:
            col.query(query_embeddings=[[0.0] * dim], n_results=1)
        return col
    except chromadb.errors.ChromaError as e:
        import logging
        logging.getLogger(__name__).warning(f"Error accessing collection: {e}. Recreating...")
        try:
            _chroma.delete_collection(name="recipes")
        except Exception:
            pass
        return _chroma.create_collection(
            name="recipes",
            metadata={"hnsw:space": "cosine"},
        )

def get_chunk_col():
    try:
        col = _chroma.get_collection(name="recipe_chunks")
        dim = 768 if EMBED_MODEL == "nomic-embed-text:latest" else 1024
        if col.count() > 0:
            col.query(query_embeddings=[[0.0] * dim], n_results=1)
        return col
    except chromadb.errors.ChromaError as e:
        import logging
        logging.getLogger(__name__).warning(f"Error accessing chunk collection: {e}. Recreating...")
        try:
            _chroma.delete_collection(name="recipe_chunks")
        except Exception:
            pass
        return _chroma.create_collection(
            name="recipe_chunks",
            metadata={"hnsw:space": "cosine"},
        )

# ─────────────────────────── SQLite (Chats) ────────────────────────
_CHAT_DB = Path("./chats.db")

def chat_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_CHAT_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    # Asegurar que las colecciones de Chroma se inicialicen
    get_col()
    get_chunk_col()
    
    with chat_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'Nueva conversación',
                history    TEXT NOT NULL DEFAULT '[]',
                updated_at INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()
    
    # Migración antigua de Chroma a SQLite (una sola vez)
    try:
        col = _chroma.get_collection("chats")
        data = col.get(include=["documents", "metadatas"])
        if data and data["ids"]:
            with chat_conn() as conn:
                for i, cid in enumerate(data["ids"]):
                    title      = data["metadatas"][i].get("title", "Chat")
                    updated_at = data["metadatas"][i].get("updated_at", 0)
                    history    = data["documents"][i] if data["documents"] else "[]"
                    conn.execute(
                        "INSERT OR IGNORE INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                        (cid, title, history, updated_at),
                    )
                conn.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error migrating Chroma to SQLite: {e}")
