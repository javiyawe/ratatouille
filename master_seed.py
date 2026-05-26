import json
import uuid
import time
import chromadb
import httpx

OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text:latest"
CHROMA_PATH = "./chroma_db"

# 50 Recetas Maestras con campos completos
RECIPES = [
    {
        "titulo": "Paella Valenciana Auténtica",
        "descripcion": "El plato más emblemático de la cocina española, cocinado con arroz bomba, pollo, conejo y verduras frescas.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Arroz Bomba", "cantidad": "400", "unidad": "g"},
            {"nombre": "Pollo troceado", "cantidad": "500", "unidad": "g"},
            {"nombre": "Conejo troceado", "cantidad": "400", "unidad": "g"},
            {"nombre": "Judía verde plana", "cantidad": "200", "unidad": "g"},
            {"nombre": "Garrofó (alubia blanca)", "cantidad": "100", "unidad": "g"},
            {"nombre": "Tomate triturado", "cantidad": "2", "unidad": "piezas"},
            {"nombre": "Azafrán en hebra", "cantidad": "1", "unidad": "pizca"},
            {"nombre": "Aceite de Oliva Virgen Extra", "cantidad": "100", "unidad": "ml"}
        ],
        "pasos": [
            "Sofreír la carne con aceite y sal hasta que esté bien dorada.",
            "Añadir la verdura y el tomate triturado. Sofreír unos minutos más.",
            "Añadir el agua y cocer durante 20 minutos para crear un caldo potente.",
            "Añadir el arroz repartiéndolo uniformemente y el azafrán.",
            "Cocinar 18-20 minutos sin remover el arroz. Reposar 5 minutos."
        ],
        "etiquetas": ["Arroz", "Tradicional", "España"]
    },
    {
        "titulo": "Sushi Nigiri de Salmón",
        "descripcion": "Delicadas piezas de arroz de sushi coronadas con láminas de salmón fresco de calidad premium.",
        "tipo_cocina": "Japonesa",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Arroz para sushi", "cantidad": "300", "unidad": "g"},
            {"nombre": "Salmón fresco", "cantidad": "200", "unidad": "g"},
            {"nombre": "Vinagre de arroz", "cantidad": "50", "unidad": "ml"},
            {"nombre": "Wasabi", "cantidad": "1", "unidad": "pizca"},
            {"nombre": "Salsa de soja", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Lavar y cocer el arroz de sushi siguiendo las instrucciones del fabricante.",
            "Mezclar el arroz con el vinagre de arroz y enfriar rápidamente.",
            "Cortar el salmón en láminas rectangulares de 3x5 cm.",
            "Formar pequeñas bolas alargadas de arroz con las manos húmedas.",
            "Colocar un punto de wasabi y la lámina de salmón encima del arroz."
        ],
        "etiquetas": ["Pescado", "Fresco", "Japón"]
    },
    {
        "titulo": "Tacos al Pastor",
        "descripcion": "Tacos mexicanos clásicos con carne de cerdo marinada en achiote y piña asada.",
        "tipo_cocina": "Mexicana",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 120},
        "ingredientes": [
            {"nombre": "Cabeza de lomo de cerdo", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Pasta de achiote", "cantidad": "100", "unidad": "g"},
            {"nombre": "Piña natural", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Tortillas de maíz", "cantidad": "12", "unidad": "unidades"},
            {"nombre": "Cebolla blanca y cilantro", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Zumo de naranja", "cantidad": "1", "unidad": "taza"}
        ],
        "pasos": [
            "Marinar la carne fileteada con achiote, naranja y especias durante 12 horas.",
            "Apilar la carne y asarla (estilo trompo o al horno).",
            "Cortar la carne en láminas finas mientras se dora.",
            "Servir sobre tortillas calientes con un trozo de piña asada.",
            "Decorar con cebolla, cilantro y salsa picante."
        ],
        "etiquetas": ["Carne", "Picante", "México"]
    },
    {
        "titulo": "Spaghetti Carbonara (Auténtica)",
        "descripcion": "La receta tradicional romana sin nata, basada en huevo, queso pecorino y guanciale.",
        "tipo_cocina": "Italiana",
        "dificultad": "Fácil",
        "porciones": 2,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "Spaghetti", "cantidad": "200", "unidad": "g"},
            {"nombre": "Guanciale o Panceta", "cantidad": "100", "unidad": "g"},
            {"nombre": "Yemas de huevo", "cantidad": "3", "unidad": "unidades"},
            {"nombre": "Queso Pecorino Romano", "cantidad": "50", "unidad": "g"},
            {"nombre": "Pimienta negra", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Cocer la pasta en agua con sal hasta que esté al dente.",
            "Dorar el guanciale en una sartén hasta que esté crujiente.",
            "Mezclar las yemas con el queso rallado y mucha pimienta.",
            "Mezclar la pasta con el guanciale y apartar del fuego.",
            "Añadir la mezcla de huevo con un poco de agua de cocción y remover hasta emulsionar."
        ],
        "etiquetas": ["Pasta", "Rápido", "Italia"]
    },
    {
        "titulo": "Ratatouille Tradicional",
        "descripcion": "Guiso provenzal de hortalizas asadas o estofadas, lleno de color y sabor mediterráneo.",
        "tipo_cocina": "Francesa",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 90},
        "ingredientes": [
            {"nombre": "Berenjena", "cantidad": "1", "unidad": "grande"},
            {"nombre": "Calabacín", "cantidad": "2", "unidad": "piezas"},
            {"nombre": "Pimiento rojo", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Tomate maduro", "cantidad": "4", "unidad": "piezas"},
            {"nombre": "Cebolla", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Hierbas provenzales", "cantidad": "1", "unidad": "cucharada"}
        ],
        "pasos": [
            "Cortar todas las verduras en rodajas finas o dados uniformes.",
            "Sofreír la cebolla y el pimiento para hacer una base.",
            "Disponer las verduras en una fuente de horno alternándolas.",
            "Aliñar con aceite, sal y hierbas provenzales.",
            "Hornear a 170ºC durante una hora hasta que estén tiernas y caramelizadas."
        ],
        "etiquetas": ["Vegetariano", "Verduras", "Francia"]
    },
    {
        "titulo": "Butter Chicken (Murgh Makhani)",
        "descripcion": "Pollo tierno marinado y cocinado en una salsa cremosa de tomate, mantequilla y especias.",
        "tipo_cocina": "India",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 50},
        "ingredientes": [
            {"nombre": "Pechuga de pollo", "cantidad": "600", "unidad": "g"},
            {"nombre": "Yogur natural", "cantidad": "150", "unidad": "g"},
            {"nombre": "Garam Masala", "cantidad": "1", "unidad": "cucharadita"},
            {"nombre": "Mantequilla", "cantidad": "50", "unidad": "g"},
            {"nombre": "Nata líquida", "cantidad": "100", "unidad": "ml"},
            {"nombre": "Tomate triturado", "cantidad": "400", "unidad": "ml"}
        ],
        "pasos": [
            "Marinar el pollo con yogur y especias durante al menos 2 horas.",
            "Cocinar el pollo al horno o en sartén hasta que esté hecho.",
            "Hacer la salsa con mantequilla, tomate y especias a fuego lento.",
            "Añadir la nata y el pollo a la salsa.",
            "Cocinar 10 minutos más y servir con pan Naan o arroz Basmati."
        ],
        "etiquetas": ["Pollo", "Especias", "India"]
    },
    {
        "titulo": "Tortilla de Patatas Española",
        "descripcion": "El clásico de los clásicos: patatas, huevos y cebolla (opcional) cocinados con amor.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 35},
        "ingredientes": [
            {"nombre": "Patatas agrias", "cantidad": "800", "unidad": "g"},
            {"nombre": "Huevos camperos", "cantidad": "6", "unidad": "piezas"},
            {"nombre": "Cebolla", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Aceite de Oliva", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Sal", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Pelar y cortar las patatas y la cebolla en láminas finas.",
            "Freír a fuego lento hasta que estén muy tiernas.",
            "Escurrir bien el aceite y mezclar con los huevos batidos.",
            "Dejar reposar la mezcla 5 minutos para que la patata absorba el huevo.",
            "Cuajar en la sartén por ambos lados al gusto (jugosa o hecha)."
        ],
        "etiquetas": ["Huevo", "Clásico", "España"]
    },
    {
        "titulo": "Lasagna a la Bolognese",
        "descripcion": "Capas de pasta fresca, ragú de carne tradicional y bechamel cremosa.",
        "tipo_cocina": "Italiana",
        "dificultad": "Difícil",
        "porciones": 6,
        "tiempos": {"total_minutos": 150},
        "ingredientes": [
            {"nombre": "Láminas de pasta", "cantidad": "12", "unidad": "unidades"},
            {"nombre": "Carne picada mixta", "cantidad": "500", "unidad": "g"},
            {"nombre": "Panceta", "cantidad": "100", "unidad": "g"},
            {"nombre": "Leche entera", "cantidad": "1", "unidad": "litro"},
            {"nombre": "Harina", "cantidad": "70", "unidad": "g"},
            {"nombre": "Queso Parmesano", "cantidad": "100", "unidad": "g"}
        ],
        "pasos": [
            "Cocinar el ragú de carne con sofrito y tomate durante 2 horas.",
            "Preparar una bechamel suave con mantequilla, harina y leche.",
            "Montar la lasagna alternando pasta, ragú y bechamel.",
            "Terminar con una capa generosa de queso parmesano.",
            "Hornear a 200ºC durante 30 minutos hasta que esté gratinada."
        ],
        "etiquetas": ["Pasta", "Horno", "Italia"]
    },
    {
        "titulo": "Tacos de Cochinita Pibil",
        "descripcion": "Cerdo deshebrado marinado en achiote y naranja agria, cocinado lentamente.",
        "tipo_cocina": "Mexicana",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 180},
        "ingredientes": [
            {"nombre": "Espaldilla de cerdo", "cantidad": "1.5", "unidad": "kg"},
            {"nombre": "Pasta de achiote", "cantidad": "100", "unidad": "g"},
            {"nombre": "Zumo de naranja agria", "cantidad": "1", "unidad": "taza"},
            {"nombre": "Cebolla morada encurtida", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Hojas de plátano", "cantidad": "para envolver", "unidad": ""}
        ],
        "pasos": [
            "Marinar la carne con el achiote diluido en naranja agria.",
            "Envolver en hojas de plátano y cocinar a fuego lento o vapor.",
            "Deshebrar la carne una vez esté muy tierna.",
            "Servir en tortillas con cebolla morada y habanero.",
            "Acompañar con frijoles refritos."
        ],
        "etiquetas": ["Cerdo", "Yucatán", "México"]
    },
    {
        "titulo": "Ramen Tonkotsu",
        "descripcion": "Sopa japonesa de fideos en un caldo denso y cremoso de huesos de cerdo cocinado 12 horas.",
        "tipo_cocina": "Japonesa",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 720},
        "ingredientes": [
            {"nombre": "Huesos de cerdo", "cantidad": "2", "unidad": "kg"},
            {"nombre": "Fideos Ramen", "cantidad": "400", "unidad": "g"},
            {"nombre": "Chashu (cerdo asado)", "cantidad": "8", "unidad": "lonchas"},
            {"nombre": "Huevo marinado (Ajitsuke Tamago)", "cantidad": "4", "unidad": "unidades"},
            {"nombre": "Cebollino", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Hervir los huesos de cerdo durante 12 horas hasta que el caldo sea blanco.",
            "Preparar el 'tare' (base de sabor) con soja y mirin.",
            "Cocer los fideos en agua hirviendo.",
            "Montar el bol: tare, caldo, fideos y toppings.",
            "Servir muy caliente con el huevo cortado por la mitad."
        ],
        "etiquetas": ["Sopa", "Intenso", "Japón"]
    },
    {
        "titulo": "Ceviche Peruano de Pescado",
        "descripcion": "Pescado blanco fresco marinado en zumo de lima, cilantro, ají y cebolla roja.",
        "tipo_cocina": "Peruana",
        "dificultad": "Fácil",
        "porciones": 2,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "Corvina o Lenguado", "cantidad": "500", "unidad": "g"},
            {"nombre": "Limas", "cantidad": "10", "unidad": "unidades"},
            {"nombre": "Cebolla roja", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Cilantro fresco", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Ají limo", "cantidad": "1", "unidad": "pieza"}
        ],
        "pasos": [
            "Cortar el pescado en cubos de 2 cm.",
            "Picar finamente el ají y el cilantro.",
            "Mezclar el pescado con sal y ají.",
            "Añadir el zumo de lima recién exprimido sin apretar demasiado.",
            "Incorporar la cebolla en pluma y servir inmediatamente con camote."
        ],
        "etiquetas": ["Pescado", "Ácido", "Perú"]
    },
    {
        "titulo": "Gazpacho Andaluz Tradicional",
        "descripcion": "Sopa fría de hortalizas batidas: tomate, pimiento, pepino y aceite de oliva.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 6,
        "tiempos": {"total_minutos": 15},
        "ingredientes": [
            {"nombre": "Tomate maduro (Pera)", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Pimiento verde", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Pepino", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Diente de ajo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Aceite de Oliva Virgen Extra", "cantidad": "100", "unidad": "ml"},
            {"nombre": "Vinagre de Jerez", "cantidad": "30", "unidad": "ml"}
        ],
        "pasos": [
            "Lavar y trocear todas las hortalizas.",
            "Triturar en la batidora hasta que sea una crema fina.",
            "Añadir el vinagre, la sal y emulsionar con el aceite de oliva.",
            "Pasar por un colador chino si se desea una textura perfecta.",
            "Enfriar en la nevera al menos 2 horas antes de servir."
        ],
        "etiquetas": ["Sopa fría", "Saludable", "España"]
    },
    {
        "titulo": "Pad Thai de Langostinos",
        "descripcion": "Fideos de arroz salteados con brotes de soja, cacahuetes, huevo y una salsa agridulce.",
        "tipo_cocina": "Tailandesa",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 30},
        "ingredientes": [
            {"nombre": "Fideos de arroz planos", "cantidad": "200", "unidad": "g"},
            {"nombre": "Langostinos", "cantidad": "10", "unidad": "unidades"},
            {"nombre": "Salsa de tamarindo", "cantidad": "3", "unidad": "cucharadas"},
            {"nombre": "Cacahuetes tostados", "cantidad": "50", "unidad": "g"},
            {"nombre": "Tofu firme", "cantidad": "100", "unidad": "g"},
            {"nombre": "Azúcar de palma", "cantidad": "2", "unidad": "cucharadas"}
        ],
        "pasos": [
            "Remojar los fideos en agua tibia hasta que estén flexibles.",
            "Saltear los langostinos y el tofu en un wok.",
            "Añadir el huevo y remover rápidamente.",
            "Incorporar los fideos y la salsa de tamarindo con azúcar.",
            "Servir con cacahuetes picados, lima y brotes de soja frescos."
        ],
        "etiquetas": ["Fideos", "Wok", "Tailandia"]
    },
    {
        "titulo": "Boeuf Bourguignon",
        "descripcion": "Estofado francés clásico de ternera cocinada en vino tinto con champiñones y cebollitas.",
        "tipo_cocina": "Francesa",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 180},
        "ingredientes": [
            {"nombre": "Carne de ternera para estofar", "cantidad": "800", "unidad": "g"},
            {"nombre": "Vino tinto (Borgoña)", "cantidad": "750", "unidad": "ml"},
            {"nombre": "Panceta ahumada", "cantidad": "150", "unidad": "g"},
            {"nombre": "Champiñones", "cantidad": "250", "unidad": "g"},
            {"nombre": "Cebollitas francesas", "cantidad": "12", "unidad": "unidades"},
            {"nombre": "Zanahoria", "cantidad": "2", "unidad": "piezas"}
        ],
        "pasos": [
            "Sellar la carne a fuego fuerte hasta que dore bien.",
            "Añadir las verduras y el vino hasta cubrir la carne.",
            "Cocinar a fuego muy lento durante 3 horas.",
            "Saltear la panceta y los champiñones por separado.",
            "Incorporar el salteado al guiso final y reducir la salsa."
        ],
        "etiquetas": ["Carne", "Guiso", "Francia"]
    },
    {
        "titulo": "Risotto de Setas y Trufa",
        "descripcion": "Arroz cremoso estilo italiano con setas de temporada y un toque aromático de trufa.",
        "tipo_cocina": "Italiana",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 35},
        "ingredientes": [
            {"nombre": "Arroz Arborio o Carnaroli", "cantidad": "200", "unidad": "g"},
            {"nombre": "Setas variadas", "cantidad": "250", "unidad": "g"},
            {"nombre": "Caldo de pollo o verduras", "cantidad": "1", "unidad": "litro"},
            {"nombre": "Mantequilla", "cantidad": "40", "unidad": "g"},
            {"nombre": "Queso Parmesano", "cantidad": "50", "unidad": "g"},
            {"nombre": "Aceite de trufa", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Sofreír las setas y reservar.",
            "Tostar el arroz en la sartén con un poco de cebolla picada.",
            "Añadir el caldo caliente poco a poco mientras se remueve.",
            "Cuando el arroz esté al dente, añadir las setas.",
            "Mantecar con mantequilla fría y queso rallado fuera del fuego."
        ],
        "etiquetas": ["Arroz", "Cremoso", "Italia"]
    },
    {
        "titulo": "Hummus de Garbanzos Clásico",
        "descripcion": "Crema suave de garbanzos cocidos, tahini, limón y ajo, ideal para dipear.",
        "tipo_cocina": "Libanesa",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 10},
        "ingredientes": [
            {"nombre": "Garbanzos cocidos", "cantidad": "400", "unidad": "g"},
            {"nombre": "Tahini (pasta de sésamo)", "cantidad": "2", "unidad": "cucharadas"},
            {"nombre": "Zumo de limón", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Diente de ajo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Comino molido", "cantidad": "1", "unidad": "pizca"},
            {"nombre": "Aceite de Oliva", "cantidad": "50", "unidad": "ml"}
        ],
        "pasos": [
            "Enjuagar bien los garbanzos si son de bote.",
            "Triturar los garbanzos con el tahini, limón y ajo.",
            "Añadir agua fría poco a poco hasta lograr la textura deseada.",
            "Servir en un plato con un chorro de aceite de oliva por encima.",
            "Espolvorear pimentón dulce y acompañar con pan de pita."
        ],
        "etiquetas": ["Vegetariano", "Legumbres", "Líbano"]
    },
    {
        "titulo": "Falafel Crujiente",
        "descripcion": "Croquetas de garbanzos crudos triturados con hierbas y especias, fritas hasta dorar.",
        "tipo_cocina": "Libanesa",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 40},
        "ingredientes": [
            {"nombre": "Garbanzos secos (remojados 24h)", "cantidad": "300", "unidad": "g"},
            {"nombre": "Cebolla", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Cilantro y perejil frescos", "cantidad": "1", "unidad": "taza"},
            {"nombre": "Ajo", "cantidad": "3", "unidad": "dientes"},
            {"nombre": "Levadura química", "cantidad": "1", "unidad": "cucharadita"}
        ],
        "pasos": [
            "Triturar los garbanzos remojados (no cocidos) con la cebolla, ajo y hierbas.",
            "La textura debe ser como arena húmeda, no puré.",
            "Dejar reposar la masa en la nevera 30 minutos.",
            "Formar pequeñas bolas y freír en abundante aceite caliente.",
            "Servir con salsa de yogur o tahini."
        ],
        "etiquetas": ["Vegano", "Frito", "Líbano"]
    },
    {
        "titulo": "Goulash Húngaro",
        "descripcion": "Guiso de carne de ternera con pimentón (paprika), verduras y un sabor profundo.",
        "tipo_cocina": "Húngara",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 120},
        "ingredientes": [
            {"nombre": "Ternera en dados", "cantidad": "800", "unidad": "g"},
            {"nombre": "Cebolla", "cantidad": "3", "unidad": "grandes"},
            {"nombre": "Paprika dulce (Pimentón)", "cantidad": "3", "unidad": "cucharadas"},
            {"nombre": "Caldo de carne", "cantidad": "500", "unidad": "ml"},
            {"nombre": "Patatas", "cantidad": "2", "unidad": "piezas"},
            {"nombre": "Semillas de alcaravea", "cantidad": "1", "unidad": "pizca"}
        ],
        "pasos": [
            "Sofreír la cebolla picada hasta que esté muy dorada.",
            "Añadir la carne y sellar.",
            "Apartar del fuego y añadir la paprika para que no se queme.",
            "Añadir el caldo y cocer a fuego lento 90 minutos.",
            "Incorporar las patatas y cocer 20 minutos más hasta que estén tiernas."
        ],
        "etiquetas": ["Carne", "Pimentón", "Hungría"]
    },
    {
        "titulo": "Moussaka Griega",
        "descripcion": "Pastel de berenjenas, carne picada de cordero y bechamel espesa, un clásico del Egeo.",
        "tipo_cocina": "Griega",
        "dificultad": "Difícil",
        "porciones": 6,
        "tiempos": {"total_minutos": 90},
        "ingredientes": [
            {"nombre": "Berenjenas", "cantidad": "3", "unidad": "piezas"},
            {"nombre": "Carne picada de cordero o ternera", "cantidad": "600", "unidad": "g"},
            {"nombre": "Tomate triturado", "cantidad": "400", "unidad": "ml"},
            {"nombre": "Queso Feta o Kefalotyri", "cantidad": "100", "unidad": "g"},
            {"nombre": "Canela en polvo", "cantidad": "1", "unidad": "pizca"}
        ],
        "pasos": [
            "Cortar berenjenas en láminas y asar al horno o freír.",
            "Cocinar la carne con tomate, cebolla y un toque de canela.",
            "Montar capas de berenjena y carne.",
            "Cubrir con una bechamel enriquecida con huevo.",
            "Hornear a 180ºC durante 45 minutos hasta dorar la superficie."
        ],
        "etiquetas": ["Berenjena", "Gratinado", "Grecia"]
    },
    {
        "titulo": "Arroz Chaufa de Pollo",
        "descripcion": "Versión peruana del arroz frito chino, con soja, cebollino y tortilla de huevo.",
        "tipo_cocina": "Chifa (Perú/China)",
        "dificultad": "Fácil",
        "porciones": 2,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "Arroz cocido del día anterior", "cantidad": "400", "unidad": "g"},
            {"nombre": "Pechuga de pollo", "cantidad": "200", "unidad": "g"},
            {"nombre": "Cebollino picado", "cantidad": "1", "unidad": "taza"},
            {"nombre": "Salsa de soja (Sillao)", "cantidad": "3", "unidad": "cucharadas"},
            {"nombre": "Aceite de sésamo", "cantidad": "1", "unidad": "cucharadita"},
            {"nombre": "Huevo", "cantidad": "2", "unidad": "unidades"}
        ],
        "pasos": [
            "Hacer una tortilla fina con los huevos y trocearla.",
            "Saltear el pollo en un wok con fuego muy fuerte.",
            "Añadir el arroz y saltear hasta que esté bien caliente.",
            "Incorporar la soja, el aceite de sésamo y el cebollino.",
            "Mezclar con la tortilla y servir inmediatamente."
        ],
        "etiquetas": ["Arroz", "Rápido", "Perú"]
    },
    {
        "titulo": "Sopa Tom Yum Goong",
        "descripcion": "Sopa tailandesa picante y ácida con langostinos, limoncillo y hojas de lima kaffir.",
        "tipo_cocina": "Tailandesa",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 25},
        "ingredientes": [
            {"nombre": "Langostinos", "cantidad": "10", "unidad": "unidades"},
            {"nombre": "Caldo de pescado", "cantidad": "1", "unidad": "litro"},
            {"nombre": "Limoncillo (Lemongrass)", "cantidad": "2", "unidad": "tallos"},
            {"nombre": "Galanga", "cantidad": "1", "unidad": "trozo"},
            {"nombre": "Pasta de chile", "cantidad": "1", "unidad": "cucharada"}
        ],
        "pasos": [
            "Hervir el caldo con el limoncillo, galanga y lima kaffir.",
            "Añadir la pasta de chile y champiñones.",
            "Incorporar los langostinos y cocinar 3 minutos.",
            "Apagar el fuego y añadir zumo de lima y salsa de pescado.",
            "Servir con cilantro fresco por encima."
        ],
        "etiquetas": ["Sopa", "Picante", "Tailandia"]
    },
    {
        "titulo": "Quiche Lorraine",
        "descripcion": "Tarta salada francesa con una base de masa quebrada, nata, huevos y bacon ahumado.",
        "tipo_cocina": "Francesa",
        "dificultad": "Media",
        "porciones": 6,
        "tiempos": {"total_minutos": 50},
        "ingredientes": [
            {"nombre": "Masa quebrada", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Bacon ahumado", "cantidad": "200", "unidad": "g"},
            {"nombre": "Nata líquida", "cantidad": "250", "unidad": "ml"},
            {"nombre": "Huevos", "cantidad": "3", "unidad": "unidades"},
            {"nombre": "Queso Gruyère", "cantidad": "100", "unidad": "g"},
            {"nombre": "Nuez moscada", "cantidad": "1", "unidad": "pizca"}
        ],
        "pasos": [
            "Pre-hornear la masa quebrada en un molde durante 10 minutos.",
            "Dorar el bacon en una sartén sin aceite.",
            "Batir los huevos con la nata y la nuez moscada.",
            "Colocar el bacon y el queso sobre la masa.",
            "Verter la mezcla de huevo y hornear 30 minutos a 180ºC."
        ],
        "etiquetas": ["Tarta salada", "Horno", "Francia"]
    },
    {
        "titulo": "Dahl de Lentejas Rojas",
        "descripcion": "Guiso indio reconfortante de lentejas peladas con cúrcuma, jengibre y leche de coco.",
        "tipo_cocina": "India",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 30},
        "ingredientes": [
            {"nombre": "Lentejas rojas", "cantidad": "250", "unidad": "g"},
            {"nombre": "Leche de coco", "cantidad": "400", "unidad": "ml"},
            {"nombre": "Cúrcuma en polvo", "cantidad": "1", "unidad": "cucharadita"},
            {"nombre": "Jengibre fresco", "cantidad": "1", "unidad": "trozo"},
            {"nombre": "Semillas de mostaza", "cantidad": "1", "unidad": "pizca"}
        ],
        "pasos": [
            "Cocer las lentejas con agua y cúrcuma hasta que se deshagan.",
            "Hacer un 'tarka' sofriendo especias en aceite hasta que salten.",
            "Añadir la leche de coco a las lentejas.",
            "Verter el aceite con especias sobre el guiso.",
            "Servir con arroz basmati y cilantro fresco."
        ],
        "etiquetas": ["Vegano", "Lentejas", "India"]
    },
    {
        "titulo": "Enchiladas Verdes",
        "descripcion": "Tortillas rellenas de pollo bañadas en salsa de tomatillo verde y queso gratinado.",
        "tipo_cocina": "Mexicana",
        "dificultad": "Media",
        "porciones": 3,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Tortillas de maíz", "cantidad": "9", "unidad": "unidades"},
            {"nombre": "Pollo deshebrado", "cantidad": "300", "unidad": "g"},
            {"nombre": "Tomatillos verdes", "cantidad": "500", "unidad": "g"},
            {"nombre": "Chile serrano", "cantidad": "2", "unidad": "unidades"},
            {"nombre": "Crema ácida", "cantidad": "100", "unidad": "ml"}
        ],
        "pasos": [
            "Cocer los tomatillos con chiles y licuar con cilantro.",
            "Pasar las tortillas por aceite caliente brevemente.",
            "Rellenar las tortillas con pollo y enrollar.",
            "Bañar con la salsa verde caliente y añadir queso.",
            "Gratinar y decorar con crema y cebolla."
        ],
        "etiquetas": ["Picante", "Pollo", "México"]
    },
    {
        "titulo": "Fish and Chips",
        "descripcion": "Filetes de pescado blanco rebozados en una masa de cerveza crujiente, servidos con patatas fritas.",
        "tipo_cocina": "Británica",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 40},
        "ingredientes": [
            {"nombre": "Bacalao o Merluza", "cantidad": "400", "unidad": "g"},
            {"nombre": "Harina", "cantidad": "200", "unidad": "g"},
            {"nombre": "Cerveza muy fría", "cantidad": "250", "unidad": "ml"},
            {"nombre": "Patatas", "cantidad": "3", "unidad": "grandes"},
            {"nombre": "Levadura química", "cantidad": "1", "unidad": "cucharadita"}
        ],
        "pasos": [
            "Hacer la masa mezclando harina, levadura y cerveza fría.",
            "Cortar las patatas y freírlas en dos tiempos (pochar y dorar).",
            "Pasar el pescado por harina y luego por el rebozado.",
            "Freír en aceite muy caliente hasta que esté dorado y crujiente.",
            "Servir con sal, vinagre de malta y puré de guisantes."
        ],
        "etiquetas": ["Pescado", "Frito", "Reino Unido"]
    },
    {
        "titulo": "Gyoza de Cerdo y Col",
        "descripcion": "Empanadillas japonesas cocinadas al vapor y luego a la plancha para una base crujiente.",
        "tipo_cocina": "Japonesa",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Masas de gyoza", "cantidad": "24", "unidad": "unidades"},
            {"nombre": "Carne de cerdo picada", "cantidad": "250", "unidad": "g"},
            {"nombre": "Col china picada", "cantidad": "100", "unidad": "g"},
            {"nombre": "Jengibre rallado", "cantidad": "1", "unidad": "cucharadita"},
            {"nombre": "Aceite de sésamo", "cantidad": "1", "unidad": "cucharadita"}
        ],
        "pasos": [
            "Mezclar la carne con la col, jengibre y condimentos.",
            "Poner una cucharadita de relleno en cada masa y cerrar con pliegues.",
            "Dorar la base de las gyozas en una sartén con aceite.",
            "Añadir un poco de agua y tapar para cocinar al vapor.",
            "Destapar y dejar que se evapore el agua para recuperar el crujiente."
        ],
        "etiquetas": ["Empanadillas", "Cena", "Japón"]
    },
    {
        "titulo": "Bibimbap Coreano",
        "descripcion": "Bol de arroz con verduras variadas, carne de ternera, huevo frito y salsa gochujang.",
        "tipo_cocina": "Coreana",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 40},
        "ingredientes": [
            {"nombre": "Arroz blanco cocido", "cantidad": "400", "unidad": "g"},
            {"nombre": "Ternera en tiras", "cantidad": "200", "unidad": "g"},
            {"nombre": "Espinacas", "cantidad": "100", "unidad": "g"},
            {"nombre": "Botes de soja", "cantidad": "100", "unidad": "g"},
            {"nombre": "Salsa Gochujang", "cantidad": "2", "unidad": "cucharadas"},
            {"nombre": "Huevo", "cantidad": "2", "unidad": "unidades"}
        ],
        "pasos": [
            "Saltear cada verdura por separado con un poco de aceite de sésamo.",
            "Cocinar la carne con soja y azúcar.",
            "Poner el arroz en el fondo de un bol.",
            "Disponer las verduras y la carne en círculos sobre el arroz.",
            "Coronar con un huevo frito y la salsa picante para mezclar todo al comer."
        ],
        "etiquetas": ["Arroz", "Saludable", "Corea"]
    },
    {
        "titulo": "Pho Bo (Sopa de Ternera)",
        "descripcion": "Sopa vietnamita de fideos de arroz con un caldo aromático de especias y ternera laminada.",
        "tipo_cocina": "Vietnamita",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 240},
        "ingredientes": [
            {"nombre": "Huesos de ternera", "cantidad": "1.5", "unidad": "kg"},
            {"nombre": "Fideos de arroz", "cantidad": "400", "unidad": "g"},
            {"nombre": "Filete de ternera fino", "cantidad": "300", "unidad": "g"},
            {"nombre": "Anís estrellado y Canela", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Brotes de soja y Albahaca", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Cocer los huesos con especias tostadas durante al menos 4 horas.",
            "Colar el caldo para que quede muy transparente.",
            "Cocer los fideos por separado.",
            "Poner fideos en el bol y la carne cruda encima (se cocina con el caldo).",
            "Verter el caldo hirviendo y añadir hierbas frescas al gusto."
        ],
        "etiquetas": ["Sopa", "Aromático", "Vietnam"]
    },
    {
        "titulo": "Steak Tartare Clásico",
        "descripcion": "Carne de vacuno cruda picada a cuchillo, aliñada con yema, alcaparras y especias.",
        "tipo_cocina": "Internacional (Francesa)",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 20},
        "ingredientes": [
            {"nombre": "Solomillo de ternera", "cantidad": "300", "unidad": "g"},
            {"nombre": "Yema de huevo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Alcaparras picadas", "cantidad": "1", "unidad": "cucharada"},
            {"nombre": "Mostaza de Dijon", "cantidad": "1", "unidad": "cucharadita"},
            {"nombre": "Salsa Perrins", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Tabasco", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Picar la carne muy fina con un cuchillo afilado (nunca picadora).",
            "En un bol sobre hielo, mezclar la yema con mostaza y aceites.",
            "Añadir la carne y el resto de ingredientes picados.",
            "Aliñar al gusto de picante y sal.",
            "Servir inmediatamente con tostadas de pan fino."
        ],
        "etiquetas": ["Carne cruda", "Gourmet", "Francia"]
    },
    {
        "titulo": "Salmorejo Cordobés",
        "descripcion": "Crema fría de tomate y pan, más espesa que el gazpacho, servida con jamón y huevo.",
        "tipo_cocina": "Española",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 15},
        "ingredientes": [
            {"nombre": "Tomates maduros", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Pan de miga blanca", "cantidad": "200", "unidad": "g"},
            {"nombre": "Aceite de Oliva Virgen Extra", "cantidad": "100", "unidad": "ml"},
            {"nombre": "Diente de ajo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Jamón serrano picado", "cantidad": "50", "unidad": "g"}
        ],
        "pasos": [
            "Triturar los tomates y colar para quitar semillas.",
            "Añadir el pan al zumo de tomate y dejar que empape.",
            "Batir con el ajo y añadir el aceite poco a poco para emulsionar.",
            "Debe quedar una textura espesa y cremosa.",
            "Servir muy frío con huevo duro y jamón picado por encima."
        ],
        "etiquetas": ["Sopa fría", "Tradicional", "España"]
    },
    {
        "titulo": "Tiramisú Clásico",
        "descripcion": "Postre italiano de capas de bizcochos empapados en café y crema de mascarpone.",
        "tipo_cocina": "Italiana",
        "dificultad": "Media",
        "porciones": 6,
        "tiempos": {"total_minutos": 40},
        "ingredientes": [
            {"nombre": "Queso Mascarpone", "cantidad": "500", "unidad": "g"},
            {"nombre": "Bizcochos de soletilla", "cantidad": "24", "unidad": "unidades"},
            {"nombre": "Huevos", "cantidad": "4", "unidad": "unidades"},
            {"nombre": "Café fuerte", "cantidad": "250", "unidad": "ml"},
            {"nombre": "Azúcar", "cantidad": "100", "unidad": "g"},
            {"nombre": "Cacao en polvo", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Separar las yemas y batirlas con el azúcar.",
            "Mezclar con el mascarpone hasta que sea una crema homogénea.",
            "Montar las claras a punto de nieve e incorporar suavemente.",
            "Mojar los bizcochos en café y disponer en la base de un molde.",
            "Alternar capas de bizcocho y crema, terminar con cacao espolvoreado."
        ],
        "etiquetas": ["Postre", "Café", "Italia"]
    },
    {
        "titulo": "Pulpo a la Gallega",
        "descripcion": "Pulpo cocido servido sobre patatas, aliñado con aceite de oliva, sal gorda y pimentón.",
        "tipo_cocina": "Española",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Pulpo cocido", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Patatas (Cachelos)", "cantidad": "4", "unidad": "grandes"},
            {"nombre": "Pimentón de la Vera", "cantidad": "1", "unidad": "cucharada"},
            {"nombre": "Aceite de Oliva Virgen Extra", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Sal gorda", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Cocer las patatas con la piel en el agua del pulpo si es posible.",
            "Cortar el pulpo en rodajas de 1 cm con tijeras.",
            "Disponer una cama de patatas peladas y cortadas en rodajas.",
            "Colocar el pulpo encima.",
            "Aliñar con sal gorda, pimentón (dulce y picante) y abundante aceite."
        ],
        "etiquetas": ["Marisco", "Galicia", "España"]
    },
    {
        "titulo": "Kebab de Pollo Casero",
        "descripcion": "Láminas de pollo marinadas con especias, asadas y servidas en pan de pita con verduras.",
        "tipo_cocina": "Turca",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Contramuslos de pollo", "cantidad": "800", "unidad": "g"},
            {"nombre": "Yogur griego", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Comino, Pimentón, Canela", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Pan de pita", "cantidad": "4", "unidad": "unidades"},
            {"nombre": "Salsa de yogur", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Marinar el pollo con yogur y especias durante 4 horas.",
            "Ensartar el pollo apretado y hornear a 200ºC.",
            "Cortar láminas finas de la capa exterior conforme se tueste.",
            "Calentar el pan de pita y rellenar con carne y ensalada.",
            "Añadir salsa de yogur y picante al gusto."
        ],
        "etiquetas": ["Carne", "Especias", "Turquía"]
    },
    {
        "titulo": "Agnolotti del Plin",
        "descripcion": "Pasta rellena tradicional del Piamonte, pequeña y con un característico pellizco.",
        "tipo_cocina": "Italiana",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 120},
        "ingredientes": [
            {"nombre": "Harina 00", "cantidad": "300", "unidad": "g"},
            {"nombre": "Yemas de huevo", "cantidad": "10", "unidad": "unidades"},
            {"nombre": "Asado de ternera", "cantidad": "200", "unidad": "g"},
            {"nombre": "Espinacas cocidas", "cantidad": "100", "unidad": "g"},
            {"nombre": "Queso Parmesano", "cantidad": "50", "unidad": "g"}
        ],
        "pasos": [
            "Hacer la masa de pasta solo con yemas y harina.",
            "Triturar la carne del asado con espinacas y queso.",
            "Estirar la pasta muy fina y poner montoncitos de relleno.",
            "Cerrar dando el 'plin' (pellizco) para sellar.",
            "Cocer 2 minutos y servir con mantequilla de salvia o el jugo del asado."
        ],
        "etiquetas": ["Pasta fresca", "Piamonte", "Italia"]
    },
    {
        "titulo": "Sopa de Cebolla Francesa",
        "descripcion": "Caldo de cebolla caramelizada con una tostada de queso fundido encima.",
        "tipo_cocina": "Francesa",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Cebollas blancas", "cantidad": "5", "unidad": "grandes"},
            {"nombre": "Mantequilla", "cantidad": "50", "unidad": "g"},
            {"nombre": "Caldo de carne", "cantidad": "1.5", "unidad": "litros"},
            {"nombre": "Pan de baguette", "cantidad": "8", "unidad": "rebanadas"},
            {"nombre": "Queso Gruyère", "cantidad": "100", "unidad": "g"}
        ],
        "pasos": [
            "Cortar cebollas en juliana y pochar con mantequilla 40 min.",
            "Deben quedar marrones y caramelizadas, no quemadas.",
            "Añadir el caldo y cocer 20 minutos más.",
            "Poner la sopa en cuencos individuales.",
            "Colocar el pan y el queso encima y gratinar al horno."
        ],
        "etiquetas": ["Sopa", "Queso", "Francia"]
    },
    {
        "titulo": "Dim Sum (Siu Mai)",
        "descripcion": "Saquitos al vapor rellenos de cerdo y gambas, típicos de la cocina cantonesa.",
        "tipo_cocina": "China",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Masas de Wanton", "cantidad": "20", "unidad": "unidades"},
            {"nombre": "Carne picada de cerdo", "cantidad": "200", "unidad": "g"},
            {"nombre": "Gambas picadas", "cantidad": "100", "unidad": "g"},
            {"nombre": "Setas Shiitake", "cantidad": "4", "unidad": "piezas"},
            {"nombre": "Salsa de ostras", "cantidad": "1", "unidad": "cucharada"}
        ],
        "pasos": [
            "Mezclar carne, gambas y setas picadas con los condimentos.",
            "Poner el relleno en el centro de la masa dejando la parte superior abierta.",
            "Formar un cilindro apretando con la mano.",
            "Cocinar en vaporera de bambú durante 8-10 minutos.",
            "Decorar con un punto de guisante o zanahoria arriba."
        ],
        "etiquetas": ["Vapor", "Aperitivo", "China"]
    },
    {
        "titulo": "Curry Verde Tailandés",
        "descripcion": "Curry aromático y picante con leche de coco, pollo y verduras verdes.",
        "tipo_cocina": "Tailandesa",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 35},
        "ingredientes": [
            {"nombre": "Pasta de curry verde", "cantidad": "2", "unidad": "cucharadas"},
            {"nombre": "Leche de coco", "cantidad": "400", "unidad": "ml"},
            {"nombre": "Pechuga de pollo", "cantidad": "300", "unidad": "g"},
            {"nombre": "Berenjena tailandesa", "cantidad": "4", "unidad": "piezas"},
            {"nombre": "Hojas de albahaca", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Freír la pasta de curry en un poco de crema de coco.",
            "Añadir el pollo y sellar.",
            "Verter el resto de leche de coco y las verduras.",
            "Cocinar hasta que el pollo esté tierno.",
            "Añadir salsa de pescado y azúcar de palma al final."
        ],
        "etiquetas": ["Picante", "Coco", "Tailandia"]
    },
    {
        "titulo": "Pierogi de Queso y Patata",
        "descripcion": "Empanadillas polacas cocidas y luego salteadas, rellenas de puré de patata y queso fresco.",
        "tipo_cocina": "Polaca",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Harina", "cantidad": "500", "unidad": "g"},
            {"nombre": "Huevo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Patatas cocidas", "cantidad": "500", "unidad": "g"},
            {"nombre": "Queso tipo Quark o Requesón", "cantidad": "250", "unidad": "g"},
            {"nombre": "Cebolla frita", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Mezclar patata machacada con queso y cebolla picada.",
            "Hacer una masa elástica con harina, huevo y agua.",
            "Cortar círculos, rellenar y cerrar los bordes.",
            "Hervir en agua hasta que floten.",
            "Saltear en mantequilla con cebolla caramelizada antes de servir."
        ],
        "etiquetas": ["Pasta", "Europa del Este", "Polonia"]
    },
    {
        "titulo": "Empanadas Argentinas de Carne",
        "descripcion": "Empanadas de masa casera rellenas de carne cortada a cuchillo, aceitunas y huevo.",
        "tipo_cocina": "Argentina",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 90},
        "ingredientes": [
            {"nombre": "Carne de ternera (Roast Beef)", "cantidad": "500", "unidad": "g"},
            {"nombre": "Cebolla blanca", "cantidad": "500", "unidad": "g"},
            {"nombre": "Huevo duro", "cantidad": "2", "unidad": "unidades"},
            {"nombre": "Aceitunas verdes", "cantidad": "50", "unidad": "g"},
            {"nombre": "Comino y Pimentón", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Sofreír mucha cebolla con la carne cortada muy pequeña.",
            "Dejar enfriar el relleno por completo (importante).",
            "Añadir el huevo y la aceituna al momento de armar.",
            "Cerrar con el repulgue tradicional.",
            "Hornear a fuego fuerte o freír en grasa."
        ],
        "etiquetas": ["Carne", "Tradicional", "Argentina"]
    },
    {
        "titulo": "Clam Chowder (Sopa de Almejas)",
        "descripcion": "Sopa cremosa de almejas estilo Nueva Inglaterra con patata y bacon.",
        "tipo_cocina": "Estadounidense",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Almejas frescas", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Patatas en dados", "cantidad": "2", "unidad": "piezas"},
            {"nombre": "Bacon", "cantidad": "100", "unidad": "g"},
            {"nombre": "Nata para cocinar", "cantidad": "200", "unidad": "ml"},
            {"nombre": "Cebolla y Apio", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Abrir las almejas al vapor y reservar el caldo.",
            "Sofreír el bacon con la cebolla y el apio.",
            "Añadir las patatas y el caldo de las almejas.",
            "Cuando la patata esté blanda, añadir la nata y el cuerpo de las almejas.",
            "Servir en un bol de pan (Bread Bowl) si se desea."
        ],
        "etiquetas": ["Marisco", "Crema", "EEUU"]
    },
    {
        "titulo": "Falafel de Remolacha",
        "descripcion": "Variante moderna y colorida del falafel tradicional usando remolacha para un sabor dulce y tierra.",
        "tipo_cocina": "Fusión / Libanesa",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Garbanzos remojados", "cantidad": "300", "unidad": "g"},
            {"nombre": "Remolacha cruda", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Tahini", "cantidad": "1", "unidad": "cucharada"},
            {"nombre": "Ajo", "cantidad": "2", "unidad": "dientes"},
            {"nombre": "Semillas de sésamo", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Triturar los garbanzos con la remolacha rallada y especias.",
            "Formar bolas pequeñas y rebozar en sésamo.",
            "Freír o hornear hasta que estén crujientes por fuera.",
            "El interior debe quedar de un color rosa vibrante.",
            "Servir con salsa de yogur y menta."
        ],
        "etiquetas": ["Vegano", "Colorido", "Líbano"]
    },
    {
        "titulo": "Ossobuco a la Milanesa",
        "descripcion": "Jarrete de ternera cortado transversalmente, guisado con vino blanco y servido con gremolata.",
        "tipo_cocina": "Italiana",
        "dificultad": "Media",
        "porciones": 2,
        "tiempos": {"total_minutos": 120},
        "ingredientes": [
            {"nombre": "Ossobuco de ternera", "cantidad": "2", "unidad": "piezas"},
            {"nombre": "Harina", "cantidad": "para rebozar", "unidad": ""},
            {"nombre": "Vino blanco seco", "cantidad": "200", "unidad": "ml"},
            {"nombre": "Caldo de carne", "cantidad": "500", "unidad": "ml"},
            {"nombre": "Limón, Ajo y Perejil (Gremolata)", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Enharinar la carne y dorar en una cazuela.",
            "Añadir el vino y dejar evaporar.",
            "Incorporar el caldo y cocer tapado a fuego lento 2 horas.",
            "La carne debe desprenderse del hueso.",
            "Servir con la gremolata fresca espolvoreada por encima."
        ],
        "etiquetas": ["Carne", "Milán", "Italia"]
    },
    {
        "titulo": "Shakshuka",
        "descripcion": "Huevos escalfados en una salsa de tomate picante con pimientos y especias del norte de África.",
        "tipo_cocina": "Oriente Medio",
        "dificultad": "Fácil",
        "porciones": 2,
        "tiempos": {"total_minutos": 30},
        "ingredientes": [
            {"nombre": "Huevos", "cantidad": "4", "unidad": "unidades"},
            {"nombre": "Tomate maduro", "cantidad": "500", "unidad": "g"},
            {"nombre": "Pimiento rojo", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Comino y Harissa", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Queso Feta", "cantidad": "50", "unidad": "g"}
        ],
        "pasos": [
            "Hacer una salsa espesa con el tomate, pimiento y especias.",
            "Hacer huecos en la salsa y cascar los huevos dentro.",
            "Tapar y cocinar hasta que la clara cuaje pero la yema siga líquida.",
            "Espolvorear queso feta y cilantro.",
            "Servir directamente en la sartén con pan de pita."
        ],
        "etiquetas": ["Huevos", "Desayuno", "Israel"]
    },
    {
        "titulo": "Sopa Miso Tradicional",
        "descripcion": "Sopa japonesa básica con pasta de miso, tofu, algas wakame y caldo dashi.",
        "tipo_cocina": "Japonesa",
        "dificultad": "Fácil",
        "porciones": 2,
        "tiempos": {"total_minutos": 15},
        "ingredientes": [
            {"nombre": "Caldo Dashi", "cantidad": "500", "unidad": "ml"},
            {"nombre": "Pasta de Miso (Blanco o Rojo)", "cantidad": "2", "unidad": "cucharadas"},
            {"nombre": "Tofu blando", "cantidad": "100", "unidad": "g"},
            {"nombre": "Alga Wakame seca", "cantidad": "1", "unidad": "cucharada"},
            {"nombre": "Cebollino", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Calentar el caldo dashi sin que llegue a hervir fuerte.",
            "Hidratar las algas en un poco de agua.",
            "Disolver el miso en un poco de caldo aparte y añadir a la olla.",
            "Añadir el tofu en dados y las algas.",
            "Servir inmediatamente con cebollino picado."
        ],
        "etiquetas": ["Sopa", "Ligero", "Japón"]
    },
    {
        "titulo": "Pastel de Choclo",
        "descripcion": "Guiso de carne y pollo cubierto con una masa de maíz tierno dulce y horneado.",
        "tipo_cocina": "Chilena",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 70},
        "ingredientes": [
            {"nombre": "Maíz tierno (Choclo) triturado", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Carne picada", "cantidad": "400", "unidad": "g"},
            {"nombre": "Pechuga de pollo cocida", "cantidad": "1", "unidad": "pieza"},
            {"nombre": "Aceitunas y Pasas", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Azúcar", "cantidad": "para espolvorear", "unidad": ""}
        ],
        "pasos": [
            "Preparar un 'pino' (sofrito de carne y cebolla).",
            "Poner el pino en la base de una fuente, añadir pollo, huevo y aceitunas.",
            "Cubrir con la pasta de maíz mezclada con albahaca.",
            "Espolvorear azúcar por encima para caramelizar.",
            "Hornear a 200ºC hasta que esté bien dorado."
        ],
        "etiquetas": ["Maíz", "Horno", "Chile"]
    },
    {
        "titulo": "Peking Duck (Pato Layaki)",
        "descripcion": "Pato asado con piel crujiente servido con crepes finos, cebollino y salsa hoisin.",
        "tipo_cocina": "China",
        "dificultad": "Difícil",
        "porciones": 4,
        "tiempos": {"total_minutos": 300},
        "ingredientes": [
            {"nombre": "Pato entero", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Miel de malta o azúcar", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Crepes finos", "cantidad": "12", "unidad": "unidades"},
            {"nombre": "Pepino y Cebollino", "cantidad": "en tiras", "unidad": ""},
            {"nombre": "Salsa Hoisin", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Escaldar el pato y secar la piel meticulosamente durante horas.",
            "Barnizar con almíbar para que caramelice.",
            "Asar colgado si es posible hasta que la piel sea como cristal.",
            "Cortar la piel y la carne en láminas.",
            "Comer enrollado en los crepes con el resto de ingredientes."
        ],
        "etiquetas": ["Pato", "Crujiente", "China"]
    },
    {
        "titulo": "Knödel de Patata",
        "descripcion": "Albóndigas de patata típicas del centro de Europa, ideales para acompañar carnes con salsa.",
        "tipo_cocina": "Alemana/Austriaca",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 45},
        "ingredientes": [
            {"nombre": "Patatas cocidas", "cantidad": "1", "unidad": "kg"},
            {"nombre": "Fécula de patata", "cantidad": "150", "unidad": "g"},
            {"nombre": "Huevo", "cantidad": "1", "unidad": "unidad"},
            {"nombre": "Pan tostado en dados", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Nuez moscada", "cantidad": "al gusto", "unidad": ""}
        ],
        "pasos": [
            "Pasar las patatas por un pasapurés mientras están calientes.",
            "Mezclar con la fécula, huevo y especias.",
            "Formar bolas grandes poniendo dados de pan en el centro.",
            "Cocer en agua con sal sin que llegue a hervir fuerte.",
            "Están listas cuando suben a la superficie."
        ],
        "etiquetas": ["Guarnición", "Patata", "Alemania"]
    },
    {
        "titulo": "Samosas de Verduras",
        "descripcion": "Triángulos de masa crujiente rellenos de patata, guisantes y especias indias.",
        "tipo_cocina": "India",
        "dificultad": "Media",
        "porciones": 4,
        "tiempos": {"total_minutos": 50},
        "ingredientes": [
            {"nombre": "Masa para samosas o Wanton", "cantidad": "12", "unidad": "unidades"},
            {"nombre": "Patatas cocidas", "cantidad": "300", "unidad": "g"},
            {"nombre": "Guisantes", "cantidad": "100", "unidad": "g"},
            {"nombre": "Curry y Garam Masala", "cantidad": "al gusto", "unidad": ""},
            {"nombre": "Jengibre", "cantidad": "1", "unidad": "cucharadita"}
        ],
        "pasos": [
            "Saltear las especias con los guisantes y la patata machacada.",
            "Cortar tiras de masa y rellenar formando triángulos.",
            "Sellar los bordes con un poco de agua.",
            "Freír en abundante aceite hasta que estén muy doradas.",
            "Servir con chutney de menta o mango."
        ],
        "etiquetas": ["Aperitivo", "Especias", "India"]
    },
    {
        "titulo": "Chili con Carne",
        "descripcion": "Guiso picante de carne picada, frijoles rojos, tomate y especias mexicanas.",
        "tipo_cocina": "Tex-Mex",
        "dificultad": "Fácil",
        "porciones": 4,
        "tiempos": {"total_minutos": 60},
        "ingredientes": [
            {"nombre": "Carne picada de ternera", "cantidad": "600", "unidad": "g"},
            {"nombre": "Frijoles rojos cocidos", "cantidad": "400", "unidad": "g"},
            {"nombre": "Tomate triturado", "cantidad": "400", "unidad": "ml"},
            {"nombre": "Chile en polvo", "cantidad": "1", "unidad": "cucharada"},
            {"nombre": "Cebolla", "cantidad": "1", "unidad": "grande"}
        ],
        "pasos": [
            "Sofreír la cebolla y el ajo, añadir la carne y dorar.",
            "Incorporar las especias y el tomate.",
            "Cocer a fuego lento 40 minutos para concentrar sabores.",
            "Añadir los frijoles y cocinar 10 minutos más.",
            "Servir con arroz blanco, crema agria y nachos."
        ],
        "etiquetas": ["Carne", "Picante", "EEUU"]
    }
]

def get_embedding(text: str):
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/embeddings", json={"model": EMBED_MODEL, "prompt": text}, timeout=120.0)
        r.raise_for_status()
        return r.json()["embedding"]
    except Exception as e:
        print(f"Error getting embedding: {e}")
        return None

def build_embed_text(r: dict):
    parts = [
        r.get("titulo") or "",
        r.get("descripcion") or "",
        r.get("tipo_cocina") or "",
        " ".join(r.get("etiquetas") or []),
        " ".join(i.get("nombre", "") for i in (r.get("ingredientes") or [])),
    ]
    return " | ".join(p for p in parts if p.strip())

def main():
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    col = client.get_or_create_collection(name="recipes", metadata={"hnsw:space": "cosine"})
    
    print(f"--- Seeding {len(RECIPES)} Master Recipes ---")
    for recipe in RECIPES:
        try:
            print(f"Ingesting: {recipe['titulo']}...")
            embed_text = build_embed_text(recipe)
            vector = get_embedding(embed_text)
            
            if vector is None:
                print(f"  Skipping {recipe['titulo']} due to embedding error")
                continue

            tiempos = recipe.get("tiempos") or {}
            metadata = {
                "titulo":             str(recipe.get("titulo") or "Sin título"),
                "dificultad":         str(recipe.get("dificultad") or "Media"),
                "tipo_cocina":        str(recipe.get("tipo_cocina") or ""),
                "total_time_minutes": int(tiempos.get("total_minutos") or 0),
                "etiquetas":          json.dumps(recipe.get("etiquetas") or [], ensure_ascii=False),
                "archivo_origen":     "master_seed"
            }
            
            col.add(
                ids=[str(uuid.uuid4())],
                embeddings=[vector],
                documents=[json.dumps(recipe, ensure_ascii=False)],
                metadatas=[metadata]
            )
            print(f"  Successfully added: {recipe['titulo']}")
            
        except Exception as e:
            print(f"  Error processing {recipe.get('titulo')}: {e}")

if __name__ == "__main__":
    main()
