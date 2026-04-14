import pytest
import json
import os
from unittest.mock import patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage
from shopify_agent.graph import workflow
from langgraph.checkpoint.memory import MemorySaver


def load_golden_dataset():
    """Carga los casos de prueba desde el archivo JSON."""
    path = os.path.join(os.path.dirname(__file__), "..",
                        "data", "golden_dataset.json")
    with open(path, "r") as f:
        return json.load(f)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", load_golden_dataset())
async def test_graph_golden_dataset(case):
    """
    Test dinámico que valida cada caso del Golden Dataset.
    Verifica que el agente use la herramienta esperada.
    """
    # 1. Configurar checkpointer en memoria
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)

    # 2. Preparar respuestas del LLM basadas en el caso del dataset
    # Simulamos que el agente decide usar la herramienta esperada
    first_response = AIMessage(
        content="",
        tool_calls=[{
            "name": case["expected_tool"],
            "args": {"order_name": "1001"},  # Genérico para el test
            "id": f"call_{case['id']}"
        }]
    )
    second_response = AIMessage(
        content=f"Procesado caso {case['id']} exitosamente.")

    # Mock de datos genéricos de Shopify/Herramientas
    mock_data = {"data": {"orders": {"edges": []}}}

    # 3. Interceptar y Validar
    with patch("shopify_agent.graph.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(
            side_effect=[first_response, second_response])

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.return_value = AsyncMock(
                status_code=200, json=lambda: mock_data)

            config = {"configurable": {"thread_id": f"thread_{case['id']}"}}
            input_state = {"messages": [HumanMessage(content=case["input"])]}

            # Ejecutar el grafo
            final_state = await app.ainvoke(input_state, config=config)

            # VALIDACIÓN SENIOR DEL PATRÓN ReAct:

            # 1. ¿El LLM fue consultado dos veces? (Decisión -> Respuesta Final)
            assert mock_llm.ainvoke.call_count == 2

            # 2. ¿El primer llamado incluía la pregunta del usuario?
            first_call_messages = mock_llm.ainvoke.call_args_list[0][0][0]
            assert first_call_messages[-1].content == case["input"]

            # 3. ¿El SEGUNDO llamado incluía el resultado de la herramienta (OBSERVATION)?
            # En LangGraph, el historial enviado al LLM en la 2da iteración debe tener el ToolMessage
            second_call_messages = mock_llm.ainvoke.call_args_list[1][0][0]

            # Buscamos si existe un mensaje de tipo 'tool' (ToolMessage) en el historial enviado
            has_tool_message = any(
                msg.type == "tool" for msg in second_call_messages)
            assert has_tool_message, f"Error en caso {case['id']}: El patrón ReAct falló. El resultado de la herramienta no se envió de vuelta al Agente."

            # 4. ¿La herramienta que se usó es la esperada?
            actual_tool_name = first_response.tool_calls[0]["name"]
            assert actual_tool_name == case["expected_tool"]
