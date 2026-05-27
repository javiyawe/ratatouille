from fastapi import APIRouter, HTTPException
import json
from app.config import TRAINING_PAIRS, LLM_MODEL, SYSTEM_PROMPT
from app.models import TrainingCompareRequest, MCPCallRequest, ChatRequest
from app.services.llm import llm
from app.services.rag import MCP_TOOLS, execute_tool, rag

router = APIRouter(tags=["training", "mcp"])

@router.get("/api/mcp/tools")
async def mcp_list_tools():
    return {
        "version": "2024-11-05",
        "description": "Ratatui MCP Server — Acceso al recetario inteligente",
        "tools": [t["function"] for t in MCP_TOOLS],
    }

@router.post("/api/mcp/call")
async def mcp_call_tool(req: MCPCallRequest):
    valid = {t["function"]["name"] for t in MCP_TOOLS}
    if req.tool not in valid:
        raise HTTPException(400, f"Tool '{req.tool}' no existe. Disponibles: {sorted(valid)}")
    result_str, sources = await execute_tool(req.tool, req.params)
    return {"result": json.loads(result_str), "sources": sources}

@router.post("/api/rag/query")
async def rag_query_endpoint(req: ChatRequest):
    result = await rag.query(req.message)
    return result

@router.get("/api/modelfile")
async def get_modelfile():
    message_block = "\n".join(
        f'MESSAGE user """{p["question"]}"""\nMESSAGE assistant """{p["answer"]}"""'
        for p in TRAINING_PAIRS
    )
    modelfile = f"""FROM {LLM_MODEL}\n\nSYSTEM \"\"\"{SYSTEM_PROMPT}\"\"\"\n\n{message_block}\n\nPARAMETER temperature 0.4\nPARAMETER top_p 0.95\nPARAMETER num_ctx 4096\n"""
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

@router.get("/api/training/pairs")
async def training_pairs():
    return {
        "total": len(TRAINING_PAIRS),
        "pairs": TRAINING_PAIRS,
    }

@router.post("/api/training/compare")
async def training_compare(req: TrainingCompareRequest):
    question = req.question.strip()
    base_msg = await llm(
        [{"role": "user", "content": question}],
        temperature=0.7,
    )
    base_response = base_msg.get("content", "")

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
