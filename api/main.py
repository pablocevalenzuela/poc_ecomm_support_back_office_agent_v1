import gradio as gr
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from ui.gradio_app import demo, logger # Reutilizamos demo y logger
from shopify_agent.graph import graph
from langchain_core.messages import HumanMessage
import os

app = FastAPI(title="Shopify Agent API & UI")

# Modelo para el endpoint de chat
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default-session"

@app.get("/")
async def root():
    return {
        "status": "ok", 
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
    
    config = {
        "configurable": {"thread_id": request.session_id},
        "metadata": {"application": "shopify-api", "environment": "cloud-run"}
    }
    
    try:
        # Invocación al grafo de LangGraph (igual que en la UI)
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
# Esto permite que un solo proceso maneje todo
app = gr.mount_gradio_app(app, demo, path="/ui")

if __name__ == "__main__":
    import uvicorn
    # Cloud Run provee la variable PORT
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Iniciando Servidor Unificado en puerto {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
