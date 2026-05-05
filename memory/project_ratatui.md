---
name: Ratatui project context
description: Stack, arquitectura y requisitos del proyecto Ratatui (recetario IA)
type: project
---

Proyecto académico de recetario inteligente con IA local. FastAPI + ChromaDB + Ollama.

**Stack:** Python/FastAPI backend, vanilla JS frontend, ChromaDB (vectores coseno), Ollama (qwen2.5:7b LLM + bge-m3 embeddings).

**Requisitos cubiertos:**
- Ollama + modelos locales: qwen2.5:7b (LLM), bge-m3 (embeddings)
- Entrenamiento IA: endpoint GET /api/modelfile genera Ollama Modelfile para personalizar el modelo
- MCP: endpoints GET /api/mcp/tools y POST /api/mcp/call exponen herramientas en formato MCP; el chat usa tool-calling real de Ollama (search_recipes, list_recipes, get_recipe)
- IA agéntica: loop de hasta 3 rondas de tool-calling antes de respuesta final streaming
- RAG: ChromaDB + embed + búsqueda coseno
- RAG + IA: chat con contexto de recetas recuperadas
- RAG empaquetado: clase RAGPipeline + endpoint POST /api/rag/query
- CSS3D: transforms 3D en recipe-item, detail-paper (pageOpen animation), welcome-logo (float3d), chef-avatar (chefBob), info-card, node-chip-premium, action-chip

**Why:** Es un proyecto de clase para demostrar estos conceptos de IA de forma práctica.
**How to apply:** Mantener todos estos requisitos cubiertos en futuras mejoras.
