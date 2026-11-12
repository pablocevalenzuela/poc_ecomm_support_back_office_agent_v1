import gradio as gr
import asyncio
import logging
import uuid
# Importamos la función de inicialización
from shopify_agent.graph import init_graph
from shopify_agent.settings import settings
from langchain_core.messages import HumanMessage

# 1. Configuración de Logging de Consola
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("SHOPIFY-AGENT")


async def predict(message, history, request: gr.Request):
    logger.info(f"--- NUEVA CONSULTA: '{message}' ---")

    # Obtenemos el grafo (se inicializa si es necesario)
    graph = await init_graph()

    if graph is None:
        return "Error: El sistema de IA no se ha inicializado correctamente."

    # Un hilo de conversación por sesión de navegador. Antes el `thread_id` era
    # la constante "local-session-001", así que TODAS las conversaciones de la
    # UI compartían el mismo historial persistido en Postgres y un simple "hola"
    # heredaba el contexto de la sesión anterior.
    # `request.session_hash` es único por carga de página; si no hay request
    # (p. ej. el cacheo de ejemplos), usamos un hilo aislado de un solo turno.
    session_hash = getattr(request, "session_hash", None)
    thread_id = f"ui-{session_hash}" if session_hash else f"ui-{uuid.uuid4().hex[:8]}"

    # El checkpointer es la única fuente del historial: no reenviamos el
    # `history` de Gradio, porque al combinarlo con el estado persistido cada
    # mensaje se guardaba dos veces y el trimmer de 15 mensajes se llenaba de
    # duplicados.
    # Metadatos para rastreo en LangSmith
    config = {
        "configurable": {"thread_id": thread_id},
        "metadata": {
            "application": "shopify-backoffice-agent",
            "environment": "localhost",
            "llm_model": settings.openrouter_agent_model
            if settings.llm_provider == "openrouter"
            else settings.llm_provider,
        }
    }

    try:
        logger.info(f"Enviando mensajes al Grafo de LangGraph (hilo: {thread_id})...")
        # Invocamos el grafo con config enriquecido
        result = await graph.ainvoke({"messages": [HumanMessage(content=message)]}, config)
        # Extraemos la respuesta final
        final_response = result["messages"][-1].content

        logger.info("Respuesta generada exitosamente.")
        return final_response

    except Exception as e:
        logger.error(f"ERROR CRÍTICO: {str(e)}", exc_info=True)
        return f"Hubo un problema técnico: {str(e)}"


def responder(pregunta, historia):
    return f"Respuesta de prueba para: {pregunta}"


# Configuración del ChatInterface con ejemplos
demo = gr.ChatInterface(
    fn=predict,
    examples=[
        "Dame el estado del pedido #1013",
        "Quisiera cancelar el pedido #1013",
        "Dame el paletizado del queso con especias con sku 2121212111",
        "¿Cuál es el stock del queso con especias?",
        "Dame información de contacto del proveedor lechería río claro",
        "Haz un pedido de 50 unidades del queso con especias con sku 2121212111"
    ],
    title="Asistente De Chatbot Para Negocios De eCommerce",
    description="Automatiza la gestión de inventario, devoluciones, gestión con proveedores y soporte interno de tu tienda online sin perder el control."
)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 7860))
    # this is a test
    logger.info(f"Iniciando servidor local en http://0.0.0.0:{port}")
    demo.launch(server_name="0.0.0.0", server_port=port)
