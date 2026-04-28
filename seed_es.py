import json
import re
import uuid
from pathlib import Path
import chromadb
import httpx

OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "bge-m3:latest"
LLM_MODEL   = "qwen2.5:7b"
CHROMA_PATH = "./chroma_db"

EXTRACTION_SYSTEM = """Eres un extractor de datos culinarios de precisión quirúrgica.
Tu ÚNICA tarea: analizar texto de receta en cualquier formato o idioma y devolver un JSON válido.

REGLAS ABSOLUTAS:
- Devuelve ÚNICAMENTE el JSON.
- Si un campo no existe, usa null o [].
- Dificultad: "Fácil", "Media", "Difícil".
"""

RECIPES_ES = [
    "Tortilla de Patatas: Ingredientes: 4 patatas medianas, 1 cebolla grande, 6 huevos, aceite de oliva virgen extra, sal. Cortar patatas y cebolla en láminas finas. Freír en abundante aceite a fuego lento hasta que estén tiernas. Escurrir el aceite. Batir huevos y mezclar con la patata y cebolla caliente. Cuajar en la sartén por ambos lados.",
    "Paella Valenciana: Ingredientes: arroz bomba (400g), pollo (500g), conejo (400g), judía verde (bajoqueta), garrofó, tomate triturado, azafrán, pimentón de la Vera, aceite, sal, romero. Sofreír la carne, añadir la verdura y el tomate. Añadir agua y cocer para hacer el caldo. Echar el arroz en cruz y cocinar 18 minutos sin remover.",
    "Gazpacho Andaluz: 1kg tomates maduros, 1 pimiento verde, 1 pepino, 2 dientes de ajo, 50g pan duro, aceite de oliva, vinagre de Jerez, sal. Triturar todo muy fino, pasar por el chino y enfriar varias horas.",
    "Salmorejo Cordobés: 1kg tomates, 200g pan de miga blanca, 100ml aceite oliva, 1 diente ajo, sal. Decorar con huevo duro y jamón picado. Triturar tomates, añadir pan, ajo y aceite al final para emulsionar.",
    "Croquetas de Jamón: 100g mantequilla, 100g harina, 1 litro leche entera, 150g jamón ibérico picado, sal, nuez moscada. Rebozado: huevo y pan rallado. Hacer una bechamel espesa cocinando la harina con la mantequilla y añadiendo leche poco a poco. Reposar la masa, formar y freír.",
    "Pulpo a la Gallega (Polbo á feira): Pulpo cocido, patatas (cachelos), pimentón dulce y picante, sal gorda, aceite de oliva virgen extra. Cortar el pulpo en rodajas sobre cama de patatas cocidas, aliñar con sal, pimentón y mucho aceite.",
    "Fabada Asturiana: 500g fabes de la Granja, 2 chorizos asturianos, 2 morcillas asturianas, 200g lacón, tocino. Remojar las fabes 12 horas. Cocer a fuego lento 'asustándolas' con agua fría un par de veces hasta que estén tiernas.",
    "Cochinillo Asado: 1 cochinillo de unos 4kg, manteca de cerdo, sal, agua. Poner el cochinillo abierto en una bandeja de barro con un poco de agua en el fondo. Hornear a 160ºC durante 3 horas regando con su propio jugo.",
    "Bacalao al Pil-Pil: 4 lomos de bacalao desalado, 250ml aceite de oliva, 5 dientes de ajo, 1 guindilla. Confitar el bacalao a fuego muy suave. Sacar el bacalao y ligar el aceite con la gelatina soltada haciendo movimientos circulares.",
    "Patatas Bravas: Patatas cortadas en dados irregulares y fritas. Salsa: aceite, harina, pimentón de la Vera (dulce y picante) y caldo de pollo. Sin tomate, la brava auténtica lleva pimentón.",
    "Pisto Manchego: Calabacín, pimiento verde, pimiento rojo, cebolla, tomate triturado, aceite de oliva. Sofreír las verduras lentamente hasta que estén pochadas, añadir el tomate y cocinar hasta que pierda el agua.",
    "Lentejas con Chorizo: Lentejas pardinas, chorizo, morcilla, tocino, patata, zanahoria, cebolla, ajo, laurel, pimentón. Cocer todo junto partiendo de agua fría hasta que las lentejas estén tiernas.",
    "Callos a la Madrileña: Callos de ternera, morro, pata, chorizo, morcilla, jamón, cebolla, ajo, guindilla, pimentón, harina. Cocinar a fuego lento durante horas hasta que el caldo esté gelatinoso y espeso.",
    "Gambas al Ajillo: 20 gambas peladas, 4 dientes de ajo laminados, 1 guindilla, aceite de oliva, sal. Dorar el ajo y la guindilla, añadir las gambas y cocinar 1 minuto a fuego fuerte.",
    "Torrijas: Pan del día anterior, leche, azúcar, canela en rama, cáscara de limón, huevos, aceite para freír. Infusionar la leche, mojar el pan, pasar por huevo y freír. Espolvorear azúcar y canela.",
    "Crema Catalana: 1l leche, 8 yemas de huevo, 200g azúcar, 40g almidón de maíz, canela, piel de limón. Cocer hasta espesar, enfriar y quemar azúcar por encima con un soplete.",
    "Arroz con Leche: 1l leche, 100g arroz, 70g azúcar, canela, piel de limón. Cocer el arroz con la leche a fuego muy lento removiendo constantemente para que suelte el almidón. Añadir azúcar al final.",
    "Churros: 1 taza de harina, 1 taza de agua, una pizca de sal, aceite para freír. Hervir el agua con sal, echar la harina de golpe y mezclar. Formar con churrera y freír en aceite muy caliente.",
    "Escalivada: Berenjena, pimiento rojo, cebolla. Asar las verduras enteras al horno o brasa. Pelar, quitar semillas y cortar en tiras. Aliñar con aceite de oliva y sal.",
    "Marmitako: 500g bonito del norte, 1kg patatas, cebolla, pimiento verde, pimiento choricero, caldo de pescado. Cascar las patatas para que suelten almidón. Añadir el bonito al final con el fuego apagado."
]

def get_embedding(text: str):
    r = httpx.post(f"{OLLAMA_URL}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text}, timeout=120.0)
    r.raise_for_status()
    return r.json()["embedding"]

def extract_with_llm(raw_text: str):
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json={
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": EXTRACTION_SYSTEM}, {"role": "user", "content": raw_text}],
        "stream": False, "options": {"temperature": 0.05}
    }, timeout=180.0)
    r.raise_for_status()
    content = r.json()["message"]["content"].strip()
    match = re.search(r"\{[\s\S]+\}", content)
    if match: content = match.group(0)
    return json.loads(content)

def build_embed_text(r: dict):
    return f"{r.get('titulo')} | {r.get('descripcion')} | {' '.join(r.get('etiquetas', []))} | {' '.join(i.get('nombre', '') for i in r.get('ingredientes', []))}"

def main():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(name="recipes", metadata={"hnsw:space": "cosine"})
    
    print(f"--- Seeding {len(RECIPES_ES)} Spanish recipes ---")
    for raw in RECIPES_ES:
        try:
            print(f"Processing: {raw[:30]}...")
            recipe = extract_with_llm(raw)
            vector = get_embedding(build_embed_text(recipe))
            
            tiempos = recipe.get("tiempos") or {}
            metadata = {
                "titulo": recipe.get("titulo", "Sin título"),
                "dificultad": str(recipe.get("dificultad", "Media")),
                "tipo_cocina": str(recipe.get("tipo_cocina", "Española")),
                "total_time_minutes": int(tiempos.get("total_minutos") or 0),
                "etiquetas": json.dumps(recipe.get("etiquetas", []), ensure_ascii=False)
            }
            col.add(ids=[str(uuid.uuid4())], embeddings=[vector], documents=[json.dumps(recipe, ensure_ascii=False)], metadatas=[metadata])
            print(f"  Done: {recipe.get('titulo')}")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == "__main__":
    main()
