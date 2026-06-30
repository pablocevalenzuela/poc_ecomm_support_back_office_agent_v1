import os
import logging
from typing import Literal
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.messages import SystemMessage, trim_messages
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from .state import AgentState
from .tools import tools
from .prompts import SYSTEM_PROMPT
from .settings import settings

# Logger para el Grafo
logger = logging.getLogger("SHOPIFY-AGENT")

# 1. Registrar todas las herramientas disponibles
tool_node = ToolNode(tools)

# 2. Configurar el LLM
llm_hf = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen2.5-72B-Instruct",
    task="chat-completion",
    huggingfacehub_api_token=settings.huggingface_api_token,
    temperature=0.01,
)
llm = ChatHuggingFace(llm=llm_hf).bind_tools(tools)

# 3. Configurar el Trimmer (Recortador de mensajes)
# Usamos un límite de mensajes más estricto para asegurar economía de tokens.
# En un entorno de producción ideal, aquí usaríamos tiktoken.
trimmer = trim_messages(
    strategy="last",
    max_tokens=15, 
    token_counter=len, 
    include_system=False,
    start_on="human",
)


# 4. Nodo del Agente


async def call_model(state: AgentState, config):
    """
    Decide si llamar a herramientas o responder al usuario.
    Aplica Message Trimming para optimizar el ROI de tokens.
    """
    # Recortamos el historial de mensajes del estado
    initial_msg_count = len(state["messages"])
    trimmed_history = trimmer.invoke(state["messages"])
    final_msg_count = len(trimmed_history) + 1  # +1 por el SystemMessage

    # Construimos el prompt final: System Prompt + Historial Recortado
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + trimmed_history

    logger.info(
        f"--- LLAMADA MODELO | Mensajes: {initial_msg_count} -> {final_msg_count} (Trimming) ---")

    response = await llm.ainvoke(messages, config)

    # Extraer metadatos de consumo
    usage = response.response_metadata.get("token_usage", {})
    if usage:
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)
        logger.info(
            f"📊 TOKEN CONSUMPTION: Input: {prompt_tokens} | Output: {completion_tokens} | Total: {total_tokens}")

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# 5. Configurar el flujo
workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges("agent", should_continue)
workflow.add_edge("tools", "agent")

# 6. Configuración de persistencia
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://user:pass@localhost/shopify_agent_db")
if "postgresql+asyncpg://" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://")

pool = AsyncConnectionPool(conninfo=DATABASE_URL, max_size=20, kwargs={
                           "autocommit": True}, open=False)

graph = None
checkpointer = None


async def init_graph():
    global graph, checkpointer
    if graph is None:
        await pool.open()
        checkpointer = AsyncPostgresSaver(pool)
        await checkpointer.setup()
        graph = workflow.compile(checkpointer=checkpointer)
    return graph
