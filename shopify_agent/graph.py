import os
from typing import Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from .state import AgentState
from .tools import tools
from .prompts import SYSTEM_PROMPT
from .settings import settings

# 1. Registrar todas las herramientas disponibles
tool_node = ToolNode(tools)

# 2. Configurar el LLM para Azure Inference / GitHub Models
llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key=settings.ai_api_key,
    base_url="https://models.inference.ai.azure.com",
    temperature=0,
).bind_tools(tools)

# 3. Nodos del Grafo
async def call_model(state: AgentState, config):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = await llm.ainvoke(messages, config)
    return {"messages": [response]}

def should_continue(state: AgentState) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END

# 4. Configurar el flujo
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

# 5. Persistencia para historial de conversación en Base de Datos
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/shopify_agent_db")

# Reemplazamos asyncpg por psycopg pool para mejor manejo de conexiones en Cloud Run
pool = AsyncConnectionPool(conninfo=DATABASE_URL, max_size=20, kwargs={"autocommit": True}, open=False)
checkpointer = AsyncPostgresSaver(pool)

# Exportamos el grafo compilado (sin checkpointer por defecto, lo inyectamos después si es necesario)
# o compilamos directamente si el pool es accesible globalmente.
graph = workflow.compile(checkpointer=checkpointer)
