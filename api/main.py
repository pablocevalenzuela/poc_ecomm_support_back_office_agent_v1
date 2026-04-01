from fastapi import FastAPI
from shopify_agent.graph import graph

app = FastAPI(title="Shopify Agent API")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Shopify Agent API Active"}

@app.post("/chat")
async def chat(message: str, session_id: str):
    # Invocación al grafo de LangGraph
    return {"response": "Procesando solicitud..."}
