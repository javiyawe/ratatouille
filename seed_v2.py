import requests
import json
import time

API_URL = "http://localhost:8000/api/recipes/save"

RECIPES = [
    {
        "titulo": "Tortilla de Patatas",
        "descripcion": "El clásico español por excelencia, jugosa y tradicional.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "patatas", "cantidad": "800", "unidad": "g"},
            {"nombre": "huevos", "cantidad": "6", "unidad": "ud"},
            {"nombre": "cebolla", "cantidad": "1", "unidad": "ud"},
            {"nombre": "aceite de oliva virgen extra", "cantidad": "500", "unidad": "ml"},
            {"nombre": "sal", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Pelar y cortar las patatas en láminas finas.",
            "Picar la cebolla.",
            "Freír patatas y cebolla a fuego lento hasta que estén tiernas.",
            "Batir los huevos en un bol grande.",
            "Escurrir el aceite y mezclar patatas con los huevos. Reposar 5 min.",
            "Cuajar la tortilla en la sartén por ambos lados."
        ]
    },
    {
        "titulo": "Paella Valenciana",
        "descripcion": "Arroz tradicional con pollo, conejo y verduras frescas.",
        "tipo_cocina": "Española",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 90},
        "ingredientes": [
            {"nombre": "arroz bomba", "cantidad": "400", "unidad": "g"},
            {"nombre": "pollo troceado", "cantidad": "500", "unidad": "g"},
            {"nombre": "conejo troceado", "cantidad": "400", "unidad": "g"},
            {"nombre": "garrofó", "cantidad": "100", "unidad": "g"},
            {"nombre": "azafrán", "cantidad": "unas hebras", "unidad": ""},
            {"nombre": "caldo de pollo", "cantidad": "1", "unidad": "l"}
        ],
        "pasos": [
            "Sofreír la carne hasta dorar.",
            "Añadir la verdura y el tomate rallado.",
            "Verter el caldo y cocinar 20 min.",
            "Echar el arroz repartiéndolo bien.",
            "Cocinar a fuego fuerte 8 min y luego lento 10 min.",
            "Dejar reposar tapado."
        ]
    },
    {
        "titulo": "Gazpacho Andaluz",
        "descripcion": "Sopa fría refrescante de hortalizas maduras.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 6,
        "tiempos": {"total_minutos": 15},
        "ingredientes": [
            {"nombre": "tomates maduros", "cantidad": "1", "unidad": "kg"},
            {"nombre": "pimiento verde", "cantidad": "1", "unidad": "ud"},
            {"nombre": "pepino", "cantidad": "1", "unidad": "ud"},
            {"nombre": "ajo", "cantidad": "1", "unidad": "diente"},
            {"nombre": "aceite de oliva", "cantidad": "50", "unidad": "ml"}
        ],
        "pasos": [
            "Lavar y trocear todas las hortalizas.",
            "Triturar en la batidora hasta que sea fino.",
            "Añadir el aceite, vinagre y sal mientras se bate.",
            "Pasar por el colador chino.",
            "Enfriar en la nevera antes de servir."
        ]
    },
    {
        "titulo": "Croquetas de Jamón",
        "descripcion": "Bechamel cremosa con virutas de jamón ibérico.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "leche entera", "cantidad": "1", "unidad": "l"},
            {"nombre": "harina", "cantidad": "100", "unidad": "g"},
            {"nombre": "mantequilla", "cantidad": "100", "unidad": "g"},
            {"nombre": "jamón ibérico", "cantidad": "150", "unidad": "g"}
        ],
        "pasos": [
            "Hacer una roux con mantequilla y harina.",
            "Añadir la leche poco a poco removiendo siempre.",
            "Echar el jamón picado.",
            "Dejar enfriar la masa varias horas.",
            "Formar las croquetas, pasar por huevo y pan rallado.",
            "Freír en abundante aceite caliente."
        ]
    },
    {
        "titulo": "Salmorejo Cordobés",
        "descripcion": "Crema fría de tomate y pan, más espesa que el gazpacho.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "tomates perita", "cantidad": "1", "unidad": "kg"},
            {"nombre": "pan de telera", "cantidad": "200", "unidad": "g"},
            {"nombre": "aceite de oliva virgen extra", "cantidad": "100", "unidad": "ml"},
            {"nombre": "ajo", "cantidad": "1", "unidad": "diente"}
        ],
        "pasos": [
            "Triturar los tomates y colar.",
            "Añadir el pan y dejar remojar.",
            "Añadir el ajo y el aceite.",
            "Triturar a máxima potencia hasta emulsionar.",
            "Servir con huevo duro y jamón picado."
        ]
    },
    {
        "titulo": "Bacalao al Pil-Pil",
        "descripcion": "Emulsión de aceite y gelatina de bacalao.",
        "tipo_cocina": "Española",
        "dificultad": "Difícil",
        "porciones": 2,
        "tiempos": {"total_minutos": 40},
        "ingredientes": [
            {"nombre": "lomos de bacalao", "cantidad": "4", "unidad": "ud"},
            {"nombre": "aceite de oliva", "cantidad": "250", "unidad": "ml"},
            {"nombre": "ajos", "cantidad": "5", "unidad": "dientes"},
            {"nombre": "guindilla", "cantidad": "1", "unidad": "ud"}
        ],
        "pasos": [
            "Dorar los ajos en el aceite y retirar.",
            "Confitar el bacalao a fuego muy suave (60°C).",
            "Retirar el bacalao y escurrir el suero.",
            "Ligar la salsa moviendo el aceite con un colador.",
            "Añadir el suero poco a poco hasta que espese."
        ]
    },
    {
        "titulo": "Lentejas con Chorizo",
        "descripcion": "Guiso reconfortante de legumbres con embutido.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 50},
        "ingredientes": [
            {"nombre": "lentejas pardinas", "cantidad": "300", "unidad": "g"},
            {"nombre": "chorizo", "cantidad": "1", "unidad": "ud"},
            {"nombre": "patata", "cantidad": "1", "unidad": "ud"},
            {"nombre": "zanahoria", "cantidad": "1", "unidad": "ud"},
            {"nombre": "pimentón de la Vera", "cantidad": "1", "unidad": "cda"}
        ],
        "pasos": [
            "Poner las lentejas en agua con las verduras troceadas.",
            "Añadir el chorizo en rodajas.",
            "Cocinar a fuego medio 40 min.",
            "Añadir un sofrito de ajo y pimentón al final.",
            "Rectificar de sal y reposar."
        ]
    },
    {
        "titulo": "Pulpo a la Gallega",
        "descripcion": "Pulpo cocido con pimentón y cachelos.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "pulpo", "cantidad": "1.5", "unidad": "kg"},
            {"nombre": "patatas", "cantidad": "4", "unidad": "uds"},
            {"nombre": "pimentón dulce y picante", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "sal gorda", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Cocer el pulpo en agua hirviendo (asustarlo 3 veces).",
            "Cocer 20-30 min hasta que esté tierno.",
            "Cocer las patatas en el mismo agua.",
            "Cortar el pulpo en rodajas con tijera.",
            "Aliñar con aceite, sal gorda y pimentón."
        ]
    },
    {
        "titulo": "Fabada Asturiana",
        "descripcion": "El guiso más famoso de Asturias con fabes y compango.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 180},
        "ingredientes": [
            {"nombre": "fabes", "cantidad": "500", "unidad": "g"},
            {"nombre": "chorizo asturiano", "cantidad": "1", "unidad": "ud"},
            {"nombre": "morcilla asturiana", "cantidad": "1", "unidad": "ud"},
            {"nombre": "lacón", "cantidad": "100", "unidad": "g"},
            {"nombre": "tocino", "cantidad": "100", "unidad": "g"}
        ],
        "pasos": [
            "Remojar las fabes 12 horas.",
            "Poner a cocer con el compango.",
            "Asustar con agua fría un par de veces.",
            "Cocinar a fuego muy lento sin remover (sacudir la olla).",
            "Reposar una hora antes de servir."
        ]
    },
    {
        "titulo": "Pescaito Frito",
        "descripcion": "Variedad de pescado pequeño rebozado y frito.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "boquerones, calamares, chopitos", "cantidad": "1", "unidad": "kg"},
            {"nombre": "harina de fuerza", "cantidad": "200", "unidad": "g"},
            {"nombre": "aceite de oliva", "cantidad": "abundante", "unidad": ""},
            {"nombre": "limón", "cantidad": "1", "unidad": "ud"}
        ],
        "pasos": [
            "Limpiar bien el pescado y secar.",
            "Enharinar ligeramente sacudiendo el exceso.",
            "Freír en aceite muy caliente por tandas.",
            "Escurrir en papel absorbente.",
            "Servir inmediatamente con limón."
        ]
    }
]

for r in RECIPES:
    try:
        resp = requests.post(API_URL, json={"recipe": r})
        if resp.status_code == 200:
            print(f"OK: {r['titulo']}")
        else:
            print(f"ERR: {r['titulo']} - {resp.text}")
    except Exception as e:
        print(f"EXC: {r['titulo']} - {e}")
    time.sleep(0.5)
