"""
Ratatui — Script de Ingesta Inteligente (Nivel 2)

Uso:
    python ingest.py                  # Procesa todos los .txt en ./recipes/
    python ingest.py recipes/mio.txt  # Procesa un archivo específico
    python ingest.py --clear          # Elimina todas las recetas de la BD

El script:
  1. Lee texto caótico y sin formato de archivos .txt
  2. Usa qwen2.5:7b para extraer un JSON estructurado (temperatura 0.05)
  3. Genera embeddings con bge-m3:latest sobre una representación semántica rica
  4. Almacena el JSON en ChromaDB con metadatos para filtrado técnico
"""

import json
import re
import sys
import uuid
from pathlib import Path

import chromadb
import httpx

OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "bge-m3:latest"
LLM_MODEL   = "qwen2.5:7b"
RECIPES_DIR = Path("recipes")
CHROMA_PATH = "./chroma_db"

# ────────────────────── Prompt de extracción estricto ─────────────────

EXTRACTION_SYSTEM = """Eres un extractor de datos culinarios de precisión quirúrgica.
Tu ÚNICA tarea: analizar texto de receta en cualquier formato o idioma y devolver un JSON válido.

REGLAS ABSOLUTAS:
- Devuelve ÚNICAMENTE el JSON. Cero texto adicional, cero markdown, cero explicaciones.
- Si un campo no existe en el texto, usa null o [] según corresponda.
- Las cantidades DEBEN ser strings que representen valores numéricos o fracciones ("200", "1/2", "al gusto").
- El JSON debe ser válido y parseable con json.loads().
- No uses comillas simples. Solo comillas dobles.

ESQUEMA OBLIGATORIO (respeta todos los campos):
{
  "titulo": "string",
  "descripcion": "string, máximo 2 oraciones describiendo el plato y su sabor",
  "porciones": 4,
  "ingredientes": [
    {
      "nombre": "string",
      "cantidad": "string",
      "unidad": "string (g|ml|taza|cucharada|cucharadita|unidad|diente|manojo|al gusto)",
      "preparacion": "string opcional (picado, en dados, rallado...)"
    }
  ],
  "pasos": [
    "string con instrucción completa del paso 1",
    "string con instrucción completa del paso 2"
  ],
  "tiempos": {
    "preparacion_minutos": 15,
    "coccion_minutos": 30,
    "reposo_minutos": 0,
    "total_minutos": 45
  },
  "etiquetas": ["tag1", "tag2", "tag3"],
  "dificultad": "Fácil",
  "tipo_cocina": "string (Italiana|Española|Mexicana|Asiática|Francesa|Internacional|etc.)",
  "tecnica_coccion": "string (horneado|salteado|hervido|fritura|vapor|asado|crudo|etc.)",
  "notas_quimicas": "string describiendo reacciones químicas relevantes: Maillard, gelificación, emulsificación, caramelización, desnaturalización proteica, etc.",
  "valor_nutricional": {
    "calorias_por_porcion": 350,
    "proteinas_g": 25,
    "carbohidratos_g": 40,
    "grasas_g": 12
  }
}

Donde dificultad debe ser exactamente uno de: "Fácil", "Media", "Difícil"
"""

# ────────────────────────── Helpers Ollama ────────────────────────────

def get_embedding(text: str) -> list:
    r = httpx.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=90.0,
    )
    r.raise_for_status()
    return r.json()["embedding"]


def extract_with_llm(raw_text: str) -> dict:
    r = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {"role": "user",   "content": f"Extrae y estructura esta receta:\n\n{raw_text}"},
            ],
            "stream": False,
            "options": {
                "temperature": 0.05,  # Casi determinista para extracción
                "top_p": 0.9,
                "num_predict": 2048,
            },
        },
        timeout=180.0,
    )
    r.raise_for_status()
    content = r.json()["message"]["content"].strip()

    # Limpiar posibles bloques de código markdown
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
    content = content.strip()

    # Extraer el primer objeto JSON válido si hay texto extra
    match = re.search(r"\{[\s\S]+\}", content)
    if match:
        content = match.group(0)

    return json.loads(content)

# ─────────────────────── Construcción del embedding ───────────────────

def build_embed_text(r: dict) -> str:
    """
    Texto semánticamente rico para generar el embedding.
    Incluye título, descripción, ingredientes, etiquetas y notas.
    """
    parts = [
        r.get("titulo") or "",
        r.get("descripcion") or "",
        r.get("tipo_cocina") or "",
        r.get("tecnica_coccion") or "",
        " ".join(r.get("etiquetas") or []),
        r.get("notas_quimicas") or "",
        " ".join(
            i.get("nombre", "") for i in (r.get("ingredientes") or [])
        ),
        " ".join((r.get("pasos") or [])[:4]),  # primeros 4 pasos dan contexto suficiente
    ]
    return " | ".join(p for p in parts if p.strip())

# ─────────────────────────── Ingesta ──────────────────────────────────

def ingest_file(path: Path, col: chromadb.Collection) -> bool:
    sep = "─" * 50
    print(f"\n{sep}")
    print(f"📄  {path.name}")
    print(sep)

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        print("  ⚠️  Archivo vacío — omitido.")
        return False

    # ── Paso 1: Extracción con LLM ──────────────────────────────────
    print("  🤖  Enviando a qwen2.5:7b para extracción estructurada...")
    try:
        recipe = extract_with_llm(raw)
    except json.JSONDecodeError as e:
        print(f"  ❌  JSON inválido en respuesta del LLM: {e}")
        return False
    except httpx.HTTPError as e:
        print(f"  ❌  Error HTTP con Ollama: {e}")
        return False

    titulo = recipe.get("titulo") or path.stem
    print(f"  ✅  Receta extraída: \"{titulo}\"")

    # Añadir metadato de origen
    recipe["archivo_origen"] = path.name

    # ── Paso 2: Generar embedding ────────────────────────────────────
    embed_text = build_embed_text(recipe)
    print(f"  🔢  Vectorizando con bge-m3 ({len(embed_text)} chars)...")
    try:
        vector = get_embedding(embed_text)
    except httpx.HTTPError as e:
        print(f"  ❌  Error al generar embedding: {e}")
        return False

    # ── Paso 3: Preparar metadatos (solo tipos primitivos para ChromaDB) ──
    tiempos = recipe.get("tiempos") or {}
    metadata = {
        "titulo":          titulo,
        "dificultad":      str(recipe.get("dificultad") or "Media"),
        "tipo_cocina":     str(recipe.get("tipo_cocina") or ""),
        "tecnica_coccion": str(recipe.get("tecnica_coccion") or ""),
        # Etiquetas como JSON string (ChromaDB no soporta arrays en metadata)
        "etiquetas":       json.dumps(recipe.get("etiquetas") or [], ensure_ascii=False),
        "total_time_minutes": int(tiempos.get("total_minutos") or 0),
        "porciones":          int(recipe.get("porciones") or 0),
        "archivo_origen":     path.name,
    }

    # ── Paso 4: Insertar en ChromaDB ─────────────────────────────────
    doc_id = str(uuid.uuid4())
    print("  💾  Guardando en ChromaDB...")
    col.add(
        ids=[doc_id],
        embeddings=[vector],
        documents=[json.dumps(recipe, ensure_ascii=False)],
        metadatas=[metadata],
    )

    print(f"  🎉  ¡Listo! ID: {doc_id[:8]}...")
    print(f"      Porciones: {recipe.get('porciones')} | "
          f"Tiempo total: {tiempos.get('total_minutos', '?')} min | "
          f"Dificultad: {recipe.get('dificultad')}")
    return True


def clear_collection(col: chromadb.Collection):
    ids = col.get(include=[])["ids"]
    if not ids:
        print("La colección ya está vacía.")
        return
    col.delete(ids=ids)
    print(f"🗑️  Eliminadas {len(ids)} recetas de la base de datos.")


# ────────────────────────────── Main ──────────────────────────────────

def main():
    print("╔══════════════════════════════════════════╗")
    print("║  Ratatui — Ingesta Inteligente       ║")
    print("╚══════════════════════════════════════════╝")

    args = sys.argv[1:]

    # Inicializar ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(
        name="recipes",
        metadata={"hnsw:space": "cosine"},
    )

    if "--clear" in args:
        clear_collection(col)
        return

    # Determinar archivos a procesar
    if args and not args[0].startswith("--"):
        files = [Path(a) for a in args if Path(a).exists()]
        if not files:
            print("❌ Ningún archivo válido especificado.")
            return
    else:
        if not RECIPES_DIR.exists():
            RECIPES_DIR.mkdir()
            print(f"📁 Directorio '{RECIPES_DIR}' creado.")
            print("   Añade archivos .txt con recetas en texto libre y vuelve a ejecutar.")
            return
        files = sorted(RECIPES_DIR.glob("*.txt"))
        if not files:
            print(f"⚠️  No hay archivos .txt en '{RECIPES_DIR}/'.")
            print("   Crea archivos con recetas en texto libre (no hace falta formato).")
            return

    print(f"\n📚 Recetas ya en BD: {col.count()}")
    print(f"📝 Archivos a procesar: {len(files)}")

    success = errors = 0
    for f in files:
        try:
            if ingest_file(f, col):
                success += 1
            else:
                errors += 1
        except Exception as e:
            print(f"  ❌ Error inesperado en {f.name}: {e}")
            errors += 1

    print(f"\n{'═'*50}")
    print(f"✅ Completado: {success} OK  |  ❌ {errors} errores")
    print(f"📊 Total recetas en BD ahora: {col.count()}")
    print("═" * 50)


if __name__ == "__main__":
    main()
