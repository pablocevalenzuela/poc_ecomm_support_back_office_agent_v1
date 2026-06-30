import asyncio
import json
import os
import time
from shopify_agent.graph import init_graph
from shopify_agent.settings import settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

# CONFIGURACIÓN DEL JUEZ (Hugging Face)
judge_llm_hf = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen2.5-72B-Instruct",
    task="chat-completion",
    huggingfacehub_api_token=settings.huggingface_api_token,
    temperature=0.01,
)
judge_llm = ChatHuggingFace(llm=judge_llm_hf)

# --- MATRIZ DE PRECIOS REALES (USD por 1M tokens - Estimación Qwen 2.5 72B) ---
PRICES = {
    "input": 0.35 / 1_000_000,   # $0.35 por 1M tokens de entrada
    "output": 0.40 / 1_000_000   # $0.40 por 1M tokens de salida
}

# Costos base por herramienta (ROI funcional/operativo - SE MANTIENE PARA LOGS)
TOOL_OPERATIONAL_COSTS = {
    "search_product_catalog": 0.008,
    "get_order_status": 0.003,
    "get_stock_by_sku": 0.002,
    "send_email_to_supplier": 0.005,
    "send_approval_email": 0.004,
    "cancel_shopify_order": 0.006,
    "default": 0.002
}


async def judge_response(query, response, rubric):
    """Llamada al LLM-as-a-Judge para calificar la efectividad holística."""
    prompt = f"""
    Actúa como un Auditor de IA Senior especializado en Sistemas Agénticos.
    
    CONTEXTO DE AUDITORÍA:
    - PREGUNTA: {query}
    - RESPUESTA: {response}
    - REQUISITOS (RÚBRICA): {rubric}
    
    CRITERIOS DE PENALIZACIÓN CRÍTICA:
    1. TRANSPARENCIA: Si la respuesta no menciona que se consultó un sistema real (Shopify, Catálogo), califica máximo con 3.
    2. PRECISIÓN: Si omite datos clave presentes en la rúbrica, califica máximo con 3.
    3. ALUCINACIÓN: Si la respuesta contradice la lógica de la herramienta, califica con 1.

    PUNTUACIÓN:
    1: Falla crítica.
    3: Correcta técnicamente pero "Caja Negra" o incompleta.
    5: Respuesta Perfecta: Precisa, amable y transparente.
    
    Devuelve solo un JSON con las claves 'score' (int) y 'reason' (str).
    """
    try:
        judge_res = await judge_llm.ainvoke(prompt)
        content = judge_res.content.replace(
            "```json", "").replace("```", "").strip()
        start = content.find("{")
        end = content.rfind("}") + 1
        return json.loads(content[start:end])
    except Exception as e:
        return {"score": 0, "reason": f"Error en el juicio: {str(e)}"}


async def run_senior_benchmark():
    print("\n" + "═"*60)
    print("🚀 AUDITORÍA AGÉNTICA HOLÍSTICA (V2 - Costos Reales de Tokens I/O)")
    print("═"*60)

    # original general golden
    # dataset_path = os.path.join("tests", "data", "golden_dataset.json")

    # golden dataset to make token economy test
    dataset_path = os.path.join(
        "tests", "data", "golden_dataset_token_economy_test.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    graph = await init_graph()
    stats = {
        "success_count": 0,
        "total_steps": 0,
        "total_cost": 0.0,
        "tool_usage": {},
        "failures": []
    }

    for case in dataset:
        print(f"\n🔍 EVALUANDO: {case['id']}")
        start_time = time.time()

        config = {
            "configurable": {"thread_id": f"bench_{int(time.time())}"},
            "metadata": {"case_id": case["id"]}
        }
        input_state = {"messages": [HumanMessage(content=case["input"])]}

        final_msg = ""
        num_steps = 0
        all_messages = []
        case_real_cost = 0.0
        case_input_tokens = 0
        case_output_tokens = 0

        async for chunk in graph.astream(input_state, config=config, stream_mode="values"):
            if "messages" in chunk:
                last_msg = chunk["messages"][-1]
                all_messages = chunk["messages"]
                num_steps += 1

                # Captura de metadatos de consumo real (de la última respuesta AI)
                if last_msg.type == "ai" and hasattr(last_msg, "usage_metadata") and last_msg.usage_metadata:
                    usage = last_msg.usage_metadata
                    i_tokens = usage.get("input_tokens", 0)
                    o_tokens = usage.get("output_tokens", 0)

                    case_input_tokens += i_tokens
                    case_output_tokens += o_tokens
                    case_real_cost += (i_tokens *
                                       PRICES["input"]) + (o_tokens * PRICES["output"])

                # Tracking de Herramientas para visibilidad de logs
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        t_name = tc['name']
                        t_args = tc.get('args', {})
                        print(f"   [🛠️ TOOL CALL]: {t_name}({t_args})")
                        stats["tool_usage"][t_name] = stats["tool_usage"].get(t_name, 0) + 1

                elif last_msg.type == "tool":
                    print(f"   [📥 TOOL RES ({last_msg.name})]: {str(last_msg.content)[:150]}...")

                if last_msg.type == "ai" and not last_msg.tool_calls:
                    final_msg = last_msg.content
                    print(f"   [💬 AGENT RESPONSE]: {final_msg[:300]}...")

        used_tools = [m.tool_calls[0]['name']
                      for m in all_messages if hasattr(m, 'tool_calls') and m.tool_calls]
        tool_ok = case['expected_tool'] in used_tools
        evaluation = await judge_response(case["input"], final_msg, case["rubric"])

        is_success = evaluation['score'] >= 4 and tool_ok
        if is_success:
            stats["success_count"] += 1
        else:
            stats["failures"].append(
                {"id": case["id"], "reason": evaluation["reason"]})

        stats["total_steps"] += num_steps
        stats["total_cost"] += case_real_cost

        print(
            f"CASE: {case['id']} | Score: {evaluation['score']}/5 | Tokens: {case_input_tokens}i/{case_output_tokens}o | Cost: ${case_real_cost:.6f} | {'⭐' if is_success else '🔴'}")

    # --- REPORTE DE ALTO NIVEL ---
    success_rate = (stats["success_count"] / len(dataset)) * 100
    print("\n" + "📊 RESUMEN EJECUTIVO")
    print(f"✅ SUCCESS RATE: {success_rate:.1f}%")
    print(f"💰 COSTO TOTAL ESTIMADO: ${stats['total_cost']:.4f} USD")
    print("\n🛠️ FRECUENCIA DE USO DE HERRAMIENTAS:")
    for t, count in sorted(stats["tool_usage"].items(), key=lambda x: x[1], reverse=True):
        print(f"  • {t:25}: {count} veces")

    print("-" * 60)
    if stats["failures"]:
        print("❌ ANÁLISIS DE FALLOS:")
        for f in stats["failures"]:
            print(f"  • {f['id']}: {f['reason'][:100]}...")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_senior_benchmark())
