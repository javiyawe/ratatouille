import json
import re
import httpx
from app.config import OLLAMA_URL, EMBED_MODEL, LLM_MODEL

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


def extract_json(text: str) -> dict:
    """Extrae JSON de texto LLM de forma robusta (con fallbacks)."""
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    raise ValueError("No se pudo extraer JSON de la respuesta del LLM")
