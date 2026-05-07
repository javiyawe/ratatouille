"""
Expande los pasos de preparación de todas las recetas usando el LLM local.
Procesa 4 recetas en paralelo. Se puede interrumpir y relanzar (guarda progreso).

Uso:
    python expand_steps.py           # expande todas
    python expand_steps.py --skip-detailed   # omite las que ya tienen pasos largos
"""
import asyncio, httpx, json, re, sys
from pathlib import Path

API        = "http://localhost:8000"
OLLAMA     = "http://localhost:11434"
LLM_MODEL  = "qwen2.5:7b"
DONE_FILE  = Path(".expand_done.json")   # IDs ya procesados
CONCURRENCY = 4                           # peticiones paralelas a Ollama

PROMPT_TMPL = """\
Eres un chef profesional y escritor de recetas. \
Tienes la siguiente receta y sus pasos actuales (que son demasiado breves). \
Tu tarea es reescribirlos con mucho más detalle para que cualquiera pueda seguirlos.

RECETA: {titulo}

INGREDIENTES:
{ings}

PASOS ACTUALES (mejorar):
{pasos}

INSTRUCCIONES PARA REESCRIBIR:
- Mínimo 6 pasos, máximo 10.
- Cada paso debe tener al menos 2-3 oraciones.
- Incluye: temperaturas exactas en °C, tiempos precisos, señales visuales/olfativas/táctiles para saber que está listo, técnica correcta, consejos para no fallar.
- Mantén el orden lógico de preparación.
- Escribe en español, tono profesional pero accesible.
- No incluyas ingredientes que no estén en la lista.

Devuelve ÚNICAMENTE un array JSON con los pasos expandidos, sin texto extra:
["Paso 1 detallado...", "Paso 2 detallado...", ...]"""


async def call_llm(prompt: str, sem: asyncio.Semaphore) -> list[str] | None:
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                r = await client.post(f"{OLLAMA}/api/chat", json={
                    "model": LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.25, "top_p": 0.9},
                })
                r.raise_for_status()
                content = r.json()["message"]["content"].strip()

            # Extraer el array JSON de la respuesta
            match = re.search(r'\[[\s\S]*\]', content)
            if not match:
                return None
            steps = json.loads(match.group(0))
            # Validar: lista de strings no vacíos
            if isinstance(steps, list) and all(isinstance(s, str) and s.strip() for s in steps):
                return steps
            return None
        except Exception as e:
            print(f"    ⚠ LLM error: {e}")
            return None


async def update_recipe(recipe_id: str, recipe: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(f"{API}/api/recipes/{recipe_id}",
                                  json={"recipe": recipe})
            return r.status_code == 200
    except Exception:
        return False


def build_prompt(recipe: dict) -> str:
    ings = "\n".join(
        f"  - {i['nombre']}: {i['cantidad']} {i['unidad']}".strip()
        for i in recipe.get("ingredientes", [])
    )
    pasos = "\n".join(f"  {n+1}. {p}" for n, p in enumerate(recipe.get("pasos", [])))
    return PROMPT_TMPL.format(
        titulo=recipe.get("titulo", ""),
        ings=ings,
        pasos=pasos,
    )


def is_already_detailed(recipe: dict) -> bool:
    pasos = recipe.get("pasos", [])
    if len(pasos) < 4:
        return False
    avg_len = sum(len(p) for p in pasos) / len(pasos)
    return avg_len > 200  # ya suficientemente detallado


async def process_one(recipe: dict, sem: asyncio.Semaphore,
                       done: set[str], skip_detailed: bool,
                       total: int, idx: int) -> None:
    rid = recipe["_id"]
    title = recipe.get("titulo", rid)

    if rid in done:
        print(f"[{idx}/{total}] ↷ Ya procesada: {title}")
        return

    if skip_detailed and is_already_detailed(recipe):
        print(f"[{idx}/{total}] ↷ Ya detallada:  {title}")
        done.add(rid)
        return

    print(f"[{idx}/{total}] ⏳ Expandiendo:  {title}")
    prompt = build_prompt(recipe)
    new_steps = await call_llm(prompt, sem)

    if not new_steps:
        print(f"[{idx}/{total}] ✗ Sin resultado: {title}")
        return

    recipe["pasos"] = new_steps
    ok = await update_recipe(rid, recipe)
    if ok:
        print(f"[{idx}/{total}] ✓ Actualizada ({len(new_steps)} pasos): {title}")
        done.add(rid)
        DONE_FILE.write_text(json.dumps(list(done)))
    else:
        print(f"[{idx}/{total}] ✗ Error API:    {title}")


async def main():
    skip_detailed = "--skip-detailed" in sys.argv

    # Cargar progreso previo
    done: set[str] = set()
    if DONE_FILE.exists():
        done = set(json.loads(DONE_FILE.read_text()))
        print(f"Progreso anterior: {len(done)} recetas ya procesadas.\n")

    # Obtener todas las recetas
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{API}/api/recipes", params={"limit": 500})
        recipes = r.json().get("recipes", [])

    print(f"Total recetas en BD: {len(recipes)}")
    print(f"Concurrencia: {CONCURRENCY} paralelas\n{'─'*50}")

    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [
        process_one(recipe, sem, done, skip_detailed, len(recipes), i + 1)
        for i, recipe in enumerate(recipes)
    ]
    await asyncio.gather(*tasks)

    print(f"\n{'─'*50}")
    print(f"Procesadas: {len(done)} / {len(recipes)}")
    if DONE_FILE.exists():
        DONE_FILE.unlink()  # limpiar al terminar


if __name__ == "__main__":
    asyncio.run(main())
