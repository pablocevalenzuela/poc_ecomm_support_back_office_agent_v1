import gradio as gr
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ui.gradio_app import demo, logger # Reutilizamos demo y logger
from shopify_agent.graph import init_graph, pool # Importamos init_graph
from langchain_core.messages import HumanMessage
from contextlib import asynccontextmanager
import os

APP_VERSION = os.getenv("APP_VERSION", "v0.0.0-dev")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lógica de inicio asíncrona
    try:
        logger.info("Inicializando Grafo y Persistencia de LangGraph...")
        # Esta llamada ocurre cuando el event loop ya está corriendo
        await init_graph()
        logger.info("Sistema listo y persistencia configurada.")
    except Exception as e:
        logger.warning(f"No se pudo configurar la persistencia persistente: {str(e)}")
    
    yield
    # Lógica de apagado
    await pool.close()

app = FastAPI(title="Shopify Agent API & UI", lifespan=lifespan)

# Modelo para el endpoint de chat
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default-session"

@app.get("/")
async def root():
    return {
        "status": "ok", 
        "version": APP_VERSION,
        "message": "Shopify Agent API & UI Active",
        "endpoints": {
            "ui": "/ui",
            "api_chat": "/chat",
            "docs": "/docs"
        }
    }

@app.post("/chat")
async def chat(request: ChatRequest):
    logger.info(f"API Call - Session: {request.session_id} - Message: {request.message}")
    
    # Obtenemos el grafo (ya inicializado en el lifespan)
    from shopify_agent.graph import graph
    if graph is None:
        raise HTTPException(status_code=503, detail="El grafo de IA no está inicializado")

    config = {
        "configurable": {"thread_id": request.session_id},
        "metadata": {"application": "shopify-api", "environment": "cloud-run"}
    }
    
    try:
        # Invocación al grafo de LangGraph
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=request.message)]}, 
            config
        )
        final_response = result["messages"][-1].content
        return {"response": final_response}
    except Exception as e:
        logger.error(f"API Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Montamos la UI de Gradio en /ui
app = gr.mount_gradio_app(app, demo, path="/ui")

if __name__ == "__main__":
    import uvicorn
    # Cloud Run provee la variable PORT
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Iniciando Servidor Unificado en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
