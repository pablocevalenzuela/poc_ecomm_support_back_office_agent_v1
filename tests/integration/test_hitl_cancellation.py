import pytest
import asyncio
from shopify_agent.graph import init_graph
from shopify_agent.state import AgentState
from langchain_core.messages import HumanMessage, AIMessage
import uuid


@pytest.mark.asyncio
async def test_hitl_cancellation_flow():
    """
    Test de Integración Opción B: Verifica el flujo HITL completo.
    1. Usuario pide cancelar.
    2. Agente envía email de solicitud y espera aprobación.
    3. Usuario aprueba.
    4. Agente ejecuta la cancelación y notifica al cliente.
    """
    # 1. Inicializar Grafo y Memoria (Persistence)
    graph = await init_graph()
    thread_id = f"test_hitl_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n[PASO 1] Iniciando solicitud de cancelación para Pedido #1010...")
    input_msg = HumanMessage(content="Quisiera cancelar mi pedido #1010")

    # Ejecutar Turno 1
    final_state = await graph.ainvoke({"messages": [input_msg]}, config=config)
    last_msg = final_state["messages"][-1]

    # Verificaciones Turno 1
    assert isinstance(last_msg, AIMessage)
    # Verificación semántica flexible
    content_lower = last_msg.content.lower()
    assert "administrador" in content_lower
    assert "aprobación" in content_lower or "solicitud" in content_lower

    # Verificación técnica: ¿Se llamó a la herramienta?
    tool_calls_1 = [m for m in final_state["messages"]
                    if hasattr(m, "tool_calls") and m.tool_calls]
    tool_names_1 = [tc["name"] for m in tool_calls_1 for tc in m.tool_calls]
    assert "send_approval_email" in tool_names_1

    print(f"Respuesta Turno 1: {last_msg.content}")

    # 2. Simular Aprobación del Usuario (Turno 2)
    print(f"\n[PASO 2] Enviando aprobación del usuario...")
    approval_msg = HumanMessage(content="apruebo")

    # Ejecutar Turno 2 en el mismo thread para mantener el estado
    final_state_2 = await graph.ainvoke({"messages": [approval_msg]}, config=config)
    last_msg_2 = final_state_2["messages"][-1]

    # Verificaciones Turno 2
    assert isinstance(last_msg_2, AIMessage)
    # El agente debería haber llamado a cancel_shopify_order
    # Buscamos en el historial si se llamó a la herramienta
    tool_calls = [m for m in final_state_2["messages"]
                  if hasattr(m, "tool_calls") and m.tool_calls]
    tool_names = [tc["name"] for m in tool_calls for tc in m.tool_calls]

    print(f"Herramientas llamadas en Turno 2: {tool_names}")
    print(f"Respuesta Final Turno 2: {last_msg_2.content}")

    # El flujo ideal es que llame a cancel_shopify_order y luego a send_customer_cancellation_email
    assert "cancel_shopify_order" in tool_names
    assert "send_customer_cancellation_email" in tool_names

    # Verificación final flexible
    final_content = last_msg_2.content.lower()
    assert "cancelación" in final_content or "cancelado" in final_content
    assert "notificación" in final_content or "correo" in final_content or "email" in final_content

if __name__ == "__main__":
    asyncio.run(test_hitl_cancellation_flow())
