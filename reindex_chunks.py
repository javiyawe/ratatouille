import asyncio
import json
from app.database import get_col, get_chunk_col
from app.services.rag import build_recipe_chunks
from app.services.llm import embed
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    logger.info("Iniciando reindexado de chunks en ChromaDB...")
    
    col = get_col()
    chunk_col = get_chunk_col()
    
    # Limpiar chunks anteriores
    if chunk_col.count() > 0:
        chunk_col.delete(where={"recipe_id": {"$ne": ""}})
        logger.info("Chunks antiguos eliminados.")
    
    total = col.count()
    if total == 0:
        logger.info("No hay recetas para reindexar.")
        return
        
    logger.info(f"Procesando {total} recetas...")
    
    # Extraer todas las recetas
    all_raw = col.get(include=["documents"])
    ids = all_raw["ids"]
    docs = all_raw["documents"]
    
    chunks_to_insert = {
        "ids": [],
        "texts": [],
        "metadatas": []
    }
    
    for rid, doc_json in zip(ids, docs):
        try:
            recipe = json.loads(doc_json)
            chunks = build_recipe_chunks(rid, recipe)
            for c_id, c_text, c_meta in chunks:
                chunks_to_insert["ids"].append(c_id)
                chunks_to_insert["texts"].append(c_text)
                chunks_to_insert["metadatas"].append(c_meta)
        except Exception as e:
            logger.error(f"Error procesando receta {rid}: {e}")
            
    total_chunks = len(chunks_to_insert["ids"])
    logger.info(f"Se generaron {total_chunks} chunks. Calculando embeddings...")
    
    # Procesar embeddings en lotes para no saturar el LLM
    batch_size = 10
    embeddings = []
    
    for i in range(0, total_chunks, batch_size):
        batch_texts = chunks_to_insert["texts"][i:i+batch_size]
        for text in batch_texts:
            vec = await embed(text)
            embeddings.append(vec)
        logger.info(f"Embeddings calculados: {len(embeddings)}/{total_chunks}")
        
    # Insertar en Chroma
    logger.info("Insertando chunks en ChromaDB...")
    
    # Chroma inserta mejor en lotes grandes (ej. 100)
    insert_batch = 100
    for i in range(0, total_chunks, insert_batch):
        chunk_col.add(
            ids=chunks_to_insert["ids"][i:i+insert_batch],
            embeddings=embeddings[i:i+insert_batch],
            documents=chunks_to_insert["texts"][i:i+insert_batch],
            metadatas=chunks_to_insert["metadatas"][i:i+insert_batch]
        )
        
    logger.info(f"¡Reindexado completado! Total de chunks insertados: {chunk_col.count()}")

if __name__ == "__main__":
    asyncio.run(main())
