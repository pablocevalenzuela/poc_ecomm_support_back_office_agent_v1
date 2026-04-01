import gradio as gr
import asyncio
import logging
from shopify_agent.graph import graph
from langchain_core.messages import HumanMessage, AIMessage

# 1. Configuración de Logging de Consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SHOPIFY-AGENT")


async def predict(message, history):
    logger.info(f"--- NUEVA CONSULTA: '{message}' ---")

    # Convertimos el historial de Gradio a mensajes de LangGraph de forma robusta
    messages = []

    for entry in history:
        # Formato antiguo: tupla/lista [user, bot]
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            user_text, bot_text = entry
            if user_text:
                messages.append(HumanMessage(content=user_text))
            if bot_text:
                messages.append(AIMessage(content=bot_text))
        # Formato nuevo: objeto con atributos role y content (o diccionario)
        elif hasattr(entry, "role"):
            if entry.role == "user":
                messages.append(HumanMessage(content=entry.content))
            elif entry.role == "assistant":
                messages.append(AIMessage(content=entry.content))
        elif isinstance(entry, dict):
            if entry.get("role") == "user":
                messages.append(HumanMessage(content=entry.get("content", "")))
            elif entry.get("role") == "assistant":
                messages.append(AIMessage(content=entry.get("content", "")))

    messages.append(HumanMessage(content=message))

    # Metadatos para rastreo en LangSmith
    config = {
        "configurable": {"thread_id": "local-session-001"},
        "metadata": {
            "application": "shopify-backoffice-agent",
            "environment": "localhost",
            "llm_model": "gpt-4o-mini"
        }
    }

    try:
        logger.info("Enviando mensajes al Grafo de LangGraph...")
        # Invocamos el grafo con config enriquecido
        result = await graph.ainvoke({"messages": messages}, config)
        # Extraemos la respuesta final
        final_response = result["messages"][-1].content

        logger.info("Respuesta generada exitosamente.")
        return final_response

    except Exception as e:
        logger.error(f"ERROR CRÍTICO: {str(e)}", exc_info=True)
        return f"Hubo un problema técnico: {str(e)}"

# Interfaz de Gradio
demo = gr.ChatInterface(
    fn=predict,
    title="eCommerce Owners Support Agent Chat (DEBUG MODE)",
    description="Ask to stock, order status and much more."
)

if __name__ == "__main__":
    logger.info("Iniciando servidor local en http://0.0.0.0:7860")
    demo.launch(server_name="0.0.0.0", server_port=7860)
