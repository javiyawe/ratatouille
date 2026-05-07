"""
demo_training.py — Demostración antes/después del entrenamiento de Ratatui.

Compara las respuestas del modelo base (qwen2.5:7b sin contexto) contra el
modelo entrenado con los pares de training_data.json y el system prompt de Ratatui.

Uso:
    python demo_training.py
    python demo_training.py --question "¿Tienes recetas con pollo?"
    python demo_training.py --all      # prueba todos los pares de entrenamiento
"""

import argparse
import json
import sys
import textwrap
import httpx

OLLAMA_URL   = "http://localhost:11434"
LLM_MODEL    = "qwen2.5:7b"
API_BASE     = "http://localhost:8000"
SEP          = "─" * 60

SYSTEM_PROMPT = """Eres Ratatui, el asistente culinario personal del usuario. Tienes acceso
a su recetario privado mediante herramientas de búsqueda. Responde siempre en español,
con tono cálido y experto. Cuando el usuario mencione ingredientes o platos, ofrécete
a buscar en el recetario."""


def wrap(text: str, width: int = 72) -> str:
    return "\n".join(textwrap.fill(line, width) for line in text.splitlines())


def ask_ollama(messages: list[dict], temperature: float = 0.7) -> str:
    with httpx.Client(timeout=120) as client:
        r = client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        r.raise_for_status()
        return r.json()["message"].get("content", "")


def ask_base(question: str) -> str:
    """Modelo base: sin system prompt, sin entrenamiento."""
    return ask_ollama([{"role": "user", "content": question}], temperature=0.7)


def ask_trained(question: str, training_pairs: list[dict]) -> str:
    """Modelo 'entrenado': system prompt + ejemplos del JSON de entrenamiento."""
    examples = "\n\n".join(
        f"Usuario: {p['question']}\nRatatui: {p['answer']}"
        for p in training_pairs[:5]
    )
    system = (
        f"{SYSTEM_PROMPT}\n\n"
        "## EJEMPLOS DE ENTRENAMIENTO\n"
        f"{examples}"
    )
    return ask_ollama(
        [
            {"role": "system", "content": system},
            {"role": "user",   "content": question},
        ],
        temperature=0.4,
    )


def compare(question: str, training_pairs: list[dict]) -> None:
    print(f"\n{'='*60}")
    print(f"PREGUNTA: {question}")
    print(SEP)

    print("\n[ANTES — Modelo base qwen2.5:7b sin entrenamiento]")
    try:
        base = ask_base(question)
        print(wrap(base))
    except Exception as e:
        print(f"  ERROR: {e}")
        base = ""

    print(f"\n{SEP}")
    print(f"[DESPUÉS — Modelo entrenado con {len(training_pairs)} pares de training_data.json]")
    try:
        trained = ask_trained(question, training_pairs)
        print(wrap(trained))
    except Exception as e:
        print(f"  ERROR: {e}")
        trained = ""

    print(f"\n{'='*60}\n")

    # Análisis rápido del diferencial
    diferencias = []
    if trained and "ratatui" in trained.lower() and "ratatui" not in base.lower():
        diferencias.append("el modelo entrenado se identifica como Ratatui")
    if trained and any(w in trained.lower() for w in ["recetario", "receta", "busco", "buscar"]):
        diferencias.append("el modelo entrenado ofrece buscar en el recetario")
    if trained and any(w in trained.lower() for w in ["hola", "¡", "!"]):
        diferencias.append("el modelo entrenado usa tono más cálido y cercano")
    trained_es = trained and any(w in trained.lower() for w in ["qué", "cómo", "así", "también"])
    base_es    = base and any(w in base.lower() for w in ["qué", "cómo", "así", "también"])
    if trained_es and not base_es:
        diferencias.append("el modelo entrenado responde en español")

    if diferencias:
        print("DIFERENCIAL OBSERVADO:")
        for d in diferencias:
            print(f"  ✓ {d.capitalize()}")
    else:
        print("DIFERENCIAL: ambas respuestas son similares para esta pregunta.")
    print()


def via_api(question: str) -> None:
    """Usa el endpoint /api/training/compare del servidor en lugar de Ollama directo."""
    print(f"\n{'='*60}")
    print(f"PREGUNTA (vía API): {question}")
    print(SEP)
    with httpx.Client(timeout=180) as client:
        r = client.post(
            f"{API_BASE}/api/training/compare",
            json={"question": question},
        )
        r.raise_for_status()
        data = r.json()

    print(f"\n[ANTES] {data['before']['label']}")
    print(wrap(data["before"]["response"]))
    print(f"\n[DESPUÉS] {data['after']['label']}")
    print(wrap(data["after"]["response"]))
    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo antes/después del entrenamiento de Ratatui")
    parser.add_argument("--question", "-q", help="Pregunta concreta a comparar")
    parser.add_argument("--all",      "-a", action="store_true", help="Prueba todos los pares de entrenamiento")
    parser.add_argument("--api",            action="store_true", help="Usa el endpoint /api/training/compare")
    args = parser.parse_args()

    with open("training_data.json", encoding="utf-8") as f:
        data = json.load(f)
    training_pairs: list[dict] = data.get("training_pairs", [])

    print(f"\n{'='*60}")
    print("  DEMO: Entrenamiento de IA con pares JSON — Ratatui")
    print(f"  Modelo: {LLM_MODEL}")
    print(f"  Pares de entrenamiento cargados: {len(training_pairs)}")
    print(f"{'='*60}")

    if args.api:
        question = args.question or "Hola, ¿quién eres?"
        via_api(question)
        return

    if args.all:
        for pair in training_pairs:
            compare(pair["question"], training_pairs)
        return

    # Por defecto, demo con 3 preguntas representativas
    demo_questions = [
        args.question or "Hola, ¿cómo te llamas?",
        "¿Qué puedo cenar si tengo poco tiempo?",
        "Tengo pollo en casa, ¿qué hago?",
    ]
    if args.question:
        demo_questions = [args.question]

    for q in demo_questions:
        compare(q, training_pairs)

    print("\nPara generar el Modelfile de Ollama con los pares de entrenamiento:")
    print("  curl http://localhost:8000/api/modelfile | python -c \"import sys,json; print(json.load(sys.stdin)['modelfile'])\" > Modelfile")
    print("  ollama create ratatui-chef -f Modelfile")
    print("  ollama run ratatui-chef\n")


if __name__ == "__main__":
    main()
