import json
import uuid
import time
import asyncio
import re
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import ChatSessionCreate, UpdateChatTitleRequest, ChatRequest
from app.database import chat_conn
from app.services.llm import llm, llm_stream
from app.services.rag import MCP_TOOLS, execute_tool, perform_search
from app.config import SYSTEM_PROMPT

router = APIRouter(tags=["chats"])

def _sse(event_type: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': event_type, **kwargs}, ensure_ascii=False)}\n\n"

_active: dict[str, tuple[asyncio.Task, asyncio.Queue]] = {}

async def async_update_title(
    chat_id: str,
    message: str,
    full_ai: str,
    _wh: list,
    _db_exists: bool,
    out: asyncio.Queue,
) -> None:
    try:
        ctx = f"Pregunta: {message}"
        if full_ai:
            ctx += f"\nRespuesta: {full_ai[:300]}"
        t_msg = await llm([
            {"role": "system", "content": (
                "Genera un título de 3-5 palabras para esta conversación culinaria. "
                "Sé específico: menciona el plato, ingrediente o técnica principal. "
                "Solo el texto, sin comillas ni puntos finales."
            )},
            {"role": "user", "content": ctx},
        ], temperature=0.2)
        chat_title = t_msg.get("content", message[:40]).strip().strip('"').strip(".")
    except Exception:
        chat_title = message[:40]

    try:
        with chat_conn() as conn:
            if _db_exists:
                conn.execute(
                    "UPDATE chats SET title=?, history=?, updated_at=? WHERE id=?",
                    (chat_title, json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                )
            else:
                conn.execute(
                    "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                    (chat_id, chat_title, json.dumps(_wh, ensure_ascii=False), int(time.time())),
                )
            conn.commit()
        await out.put(_sse("title", value=chat_title))
    except Exception:
        pass
    finally:
        await out.put(None)
        _active.pop(chat_id, None)

async def _process_chat(
    chat_id: str,
    message: str,
    history: list,
    is_new: bool,
    old_title: str,
    out: asyncio.Queue,
) -> None:
    full_ai  = ""
    _src: list[dict] = []

    _wh = history + [{"role": "user", "content": message}]
    _db_exists = not is_new
    try:
        with chat_conn() as conn:
            if is_new:
                conn.execute(
                    "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, ?, ?)",
                    (chat_id, old_title or "Nueva conversación",
                     json.dumps(_wh, ensure_ascii=False), int(time.time())),
                )
                _db_exists = True
            else:
                conn.execute(
                    "UPDATE chats SET history=?, updated_at=? WHERE id=?",
                    (json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                )
            conn.commit()
    except Exception:
        pass

    async def emit(t: str, **kw):
        await out.put(_sse(t, **kw))

    try:
        is_greeting = bool(re.search(
            r"\b(hola|buenos\s+dias|buenas\s+tardes|buenas\s+noches|que\s+tal|cómo\s+estás|como\s+estas|gracias|muchas\s+gracias|adiós|adios|chao|saludos)\b",
            message, re.IGNORECASE
        )) and len(message) < 50

        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in history[-10:]:
            msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": message})

        if is_greeting:
            await emit("thought", value="Saludando...")
            async for chunk in llm_stream(msgs, temperature=0.5):
                if chunk == "\n\n[DONE]":
                    break
                elif chunk:
                    full_ai += chunk
                    await emit("token", value=chunk)
            await emit("done")

        else:
            await emit("thought", value="Analizando consulta...")
            agent_msg  = await llm(msgs, temperature=0.2, tools=MCP_TOOLS)
            content    = agent_msg.get("content") or ""
            tool_calls = agent_msg.get("tool_calls") or []

            if tool_calls:
                msgs.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                all_sources = []
                for tc in tool_calls:
                    func        = tc.get("function", {})
                    tool_name   = func.get("name", "")
                    raw_args    = func.get("arguments", {})
                    tool_params = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")

                    if tool_name == "search_recipes":
                        label = f"Buscando «{tool_params.get('query','…')}» en el recetario"
                    elif tool_name == "get_recipe":
                        label = "Consultando detalles de la receta"
                    else:
                        label = tool_name.replace("_", " ").capitalize()

                    await emit("thought", value=f"{label}…")
                    result_str, sources = await execute_tool(tool_name, tool_params)
                    all_sources.extend(sources)
                    msgs.append({"role": "tool", "content": result_str})

                if all_sources:
                    unique = list({s["id"]: s for s in all_sources}.values())
                    _src   = [{"id": s["id"], "titulo": s["titulo"]} for s in unique]
                    await emit("sources", value=_src)

                    numbered_list = "\n".join(f"- {s['titulo']} (ID: {s['id']})" for s in _src)
                    example = _src[0]
                    msgs.append({
                        "role": "system",
                        "content": (
                            f"Recetas disponibles en el libro:\n{numbered_list}\n\n"
                            "Al mencionar cualquier receta usa OBLIGATORIAMENTE el formato Markdown de enlace con ref:. "
                            f"Ejemplo: \"[{example['titulo']}](ref:{example['id']})\".\n"
                            "NO uses otros formatos como [1]."
                        )
                    })
                else:
                    msgs.append({
                        "role": "system",
                        "content": "La búsqueda no ha devuelto NINGUNA receta. RESPONDE EXPLÍCITAMENTE que no tienes ninguna receta que coincida en el libro. NO INVENTES RECETAS BAJO NINGÚN CONCEPTO."
                    })

                await emit("thought", value="Preparando la respuesta…")
                async for chunk in llm_stream(msgs, temperature=0.1):
                    if chunk == "\n\n[DONE]":
                        break
                    elif chunk:
                        full_ai += chunk
                        await emit("token", value=chunk)
                await emit("done")

            else:
                await emit("thought", value="Buscando en el recetario...")
                try:
                    docs = await perform_search(message, 4)
                except Exception:
                    docs = []
                
                if docs:
                    for r in docs:
                        if r.get("_id"):
                            _src.append({"id": r["_id"], "titulo": r["titulo"]})
                    
                    unique = list({s["id"]: s for s in _src}.values())
                    _src   = [{"id": s["id"], "titulo": s["titulo"]} for s in unique]
                    await emit("sources", value=_src)

                    numbered_list = "\n".join(f"- {s['titulo']} (ID: {s['id']})" for s in _src)
                    example = _src[0]
                    msgs.append({
                        "role": "system",
                        "content": (
                            f"Recetas del libro (CONTEXTO):\n{json.dumps(docs, ensure_ascii=False)}\n\n"
                            f"Recetas disponibles:\n{numbered_list}\n\n"
                            "Al mencionar cualquier receta usa OBLIGATORIAMENTE el formato Markdown de enlace con ref:. "
                            f"Ejemplo: \"[{example['titulo']}](ref:{example['id']})\".\n"
                            "NO uses otros formatos."
                        )
                    })
                    
                    await emit("thought", value="Preparando la respuesta…")
                    async for chunk in llm_stream(msgs, temperature=0.1):
                        if chunk == "\n\n[DONE]":
                            break
                        elif chunk:
                            full_ai += chunk
                            await emit("token", value=chunk)
                    await emit("done")
                else:
                    msgs.append({
                        "role": "system",
                        "content": "No se encontraron recetas en el libro. Si el usuario pide un plato, responde explícitamente que NO lo tienes. NO INVENTES RECETAS."
                    })
                    
                    await emit("thought", value="Respondiendo...")
                    async for chunk in llm_stream(msgs, temperature=0.1):
                        if chunk == "\n\n[DONE]":
                            break
                        elif chunk:
                            full_ai += chunk
                            await emit("token", value=chunk)
                    await emit("done")

    except Exception as exc:
        await emit("error", value=str(exc))

    finally:
        if full_ai:
            _wh.append({"role": "assistant", "content": full_ai, "sources": _src})

        if is_new or old_title in ("", "Nueva conversación"):
            asyncio.create_task(async_update_title(chat_id, message, full_ai, _wh, _db_exists, out))
        else:
            try:
                with chat_conn() as conn:
                    conn.execute(
                        "UPDATE chats SET history=?, updated_at=? WHERE id=?",
                        (json.dumps(_wh, ensure_ascii=False), int(time.time()), chat_id),
                    )
                    conn.commit()
            except Exception:
                pass
            await out.put(None)
            _active.pop(chat_id, None)


@router.get("/api/chats")
async def list_chats():
    with chat_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return {"chats": [dict(r) for r in rows]}

@router.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    chat_id = req.chat_id or str(uuid.uuid4())

    if chat_id not in _active:
        with chat_conn() as conn:
            row = conn.execute(
                "SELECT title, history FROM chats WHERE id=?", (chat_id,)
            ).fetchone()
        if row:
            history   = json.loads(row["history"])
            is_new    = False
            old_title = row["title"]
        else:
            history   = []
            is_new    = True
            old_title = ""

        out: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(
            _process_chat(chat_id, req.message, history, is_new, old_title, out)
        )
        _active[chat_id] = (task, out)
    else:
        _, out = _active[chat_id]

    async def stream():
        yield _sse("chat_id", value=chat_id)
        while True:
            try:
                item = await asyncio.wait_for(out.get(), timeout=300.0)
            except asyncio.TimeoutError:
                break
            if item is None:
                break
            yield item

    return StreamingResponse(stream(), media_type="text/event-stream")

@router.post("/api/chats")
async def create_chat(req: ChatSessionCreate):
    chat_id = str(uuid.uuid4())
    with chat_conn() as conn:
        conn.execute(
            "INSERT INTO chats (id, title, history, updated_at) VALUES (?, ?, '[]', ?)",
            (chat_id, req.title, int(time.time())),
        )
        conn.commit()
    return {"id": chat_id, "title": req.title}

@router.get("/api/chats/{chat_id}")
async def get_chat_history(chat_id: str):
    with chat_conn() as conn:
        row = conn.execute(
            "SELECT history FROM chats WHERE id=?", (chat_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404)
    return {"id": chat_id, "history": json.loads(row["history"])}

@router.put("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, req: UpdateChatTitleRequest):
    with chat_conn() as conn:
        cur = conn.execute(
            "UPDATE chats SET title=? WHERE id=?",
            (req.title.strip()[:120], chat_id),
        )
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"id": chat_id, "title": req.title.strip()[:120]}

@router.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    with chat_conn() as conn:
        cur = conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404)
    return {"status": "deleted"}
