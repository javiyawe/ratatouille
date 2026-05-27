import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models import (
    SearchRequest, ExtractRequest, SaveRecipeRequest, 
    UpdateRecipeRequest, RefineRecipeRequest
)
from app.database import get_col
from app.services.llm import llm_stream, llm, extract_json, embed
from app.services.rag import perform_search, store_recipe_async, build_embed_text, normalize_recipe
from app.config import EXTRACTION_SCHEMA

router = APIRouter(tags=["recipes"])

@router.get("/api/stats")
async def stats():
    return {"total_recipes": get_col().count()}

@router.get("/api/recipes")
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

@router.post("/api/search")
async def search(req: SearchRequest):
    recipes = await perform_search(
        query=req.query,
        n_results=req.n_results,
        max_time=req.max_time,
        difficulty=req.difficulty,
    )
    return {"recipes": recipes, "query": req.query}

@router.post("/api/recipes/extract")
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

@router.post("/api/recipes/save")
async def recipe_save(req: SaveRecipeRequest):
    doc_id = await store_recipe_async(req.recipe)
    return {"id": doc_id}

@router.put("/api/recipes/{recipe_id}")
async def recipe_update(recipe_id: str, req: UpdateRecipeRequest):
    vector = await embed(build_embed_text(req.recipe))
    get_col().update(
        ids=[recipe_id],
        embeddings=[vector],
        documents=[json.dumps(req.recipe, ensure_ascii=False)],
    )
    return {"status": "updated"}

@router.delete("/api/recipes/{recipe_id}")
async def recipe_delete(recipe_id: str):
    data = get_col().get(ids=[recipe_id])
    if not data["ids"]:
        raise HTTPException(404, "Receta no encontrada")
    get_col().delete(ids=[recipe_id])
    return {"status": "deleted"}

@router.post("/api/recipes/refine")
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
