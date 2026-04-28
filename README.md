# 🐀 Ratatouille — Recetario Inteligente & Asistente Culinario

Bienvenido a **Ratatouille**, una herramienta gastronómica de vanguardia diseñada para amantes de la cocina que buscan precisión, inspiración y una pizca de alma francesa. Detrás de esta interfaz minimalista se encuentra el pequeño gran Chef Ratatouille, listo para ayudarte a gestionar tu libro de cocina y crear platos inolvidables.

## ✨ Características Principales

-   **📖 Libro de Cocina Inteligente**: Una vista dividida (*split-view*) premium donde puedes organizar tus recetas alfabéticamente, por tiempo o dificultad.
-   **💬 Chat con Ratatouille (RAG)**: Un asistente culinario que conoce tus recetas. Pídele que las adapte (ej: para 5 personas), que sugiera variaciones o que fusione técnicas mediante su "Modo Alquimia".
-   **🧠 Ingesta Inteligente**: Pega cualquier texto de receta y deja que Ratatouille lo analice, extraiga los ingredientes y pasos, y lo guarde automáticamente en tu base de datos vectorial.
-   **🌊 Streaming en Tiempo Real**: Siente la pasión del Chef mientras escribe sus respuestas palabra por palabra, mostrando siempre las fuentes (nodos de referencia) en las que se basa.
-   **🎨 Estética Premium**: Un diseño minimalista basado en "papel y tinta", con tipografías curadas y micro-animaciones que elevan la experiencia de usuario.

## 🚀 Tecnologías Utilizadas

-   **Backend**: FastAPI (Python)
-   **Base de Datos Vectorial**: ChromaDB (BGE-M3 Embeddings)
-   **IA / LLM**: Ollama (Llama 3 / Mistral)
-   **Frontend**: Vanilla JS, HTML5, CSS3 (con soporte para Markdown vía Marked.js)
-   **Estilos**: Tipografías de Google Fonts (Crimson Pro & Outfit)

## 🛠 Instalación y Uso

1.  **Requisitos**: Tener instalado Python 3.10+ y [Ollama](https://ollama.com/).
2.  **Modelos de Ollama**:
    ```bash
    ollama pull llama3 # O el modelo que prefieras configurar en main.py
    ```
3.  **Instalar dependencias**:
    ```bash
    pip install fastapi uvicorn chromadb httpx pydantic
    ```
4.  **Ejecutar**:
    ```bash
    python -m uvicorn main:app --reload
    ```
5.  **Acceso**: Abre `http://localhost:8000` en tu navegador.

## 👨‍🍳 Filosofía del Chef
> "Cualquiera puede cocinar, pero solo el intrépido puede ser un gran chef."

Este proyecto no es solo una base de datos; es un compañero de cocina que entiende la alquimia detrás de cada ingrediente. ¡Bon appétit!
