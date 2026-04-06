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

# 2. Configurar el LLM
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

# 4. Configurar el flujo (Sin compilar todavía)
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

# 5. Configuración de persistencia diferida
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/shopify_agent_db")
if "postgresql+asyncpg://" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

pool = AsyncConnectionPool(conninfo=DATABASE_URL, max_size=20, kwargs={"autocommit": True}, open=False)

# Variables globales que se inicializarán en el lifespan de FastAPI
graph = None
checkpointer = None

async def init_graph():
    """Inicializa el pool, el checkpointer y compila el grafo dentro de un loop de asyncio."""
    global graph, checkpointer
    if graph is None:
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        graph = workflow.compile(checkpointer=checkpointer)
    return graph
