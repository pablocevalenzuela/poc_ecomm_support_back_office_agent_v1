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

# --- MATRIZ DE COSTOS (Estimación ROI por herramienta) ---
TOOL_COSTS = {
    "search_product_catalog": 0.008,  # RAG (Embeddings + Contexto Pesado)
    "get_order_status": 0.003,       # Shopify API (Llamada externa)
    "get_stock_by_sku": 0.002,       # Shopify API (Ligera)
    "send_email_to_supplier": 0.005,  # Email (Proceso externo + SMTP)
    "send_approval_email": 0.004,    # Email (Proceso externo)
    "cancel_shopify_order": 0.006,   # Mutación Crítica
    "default": 0.002                 # Paso de razonamiento base
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
    print("🚀 AUDITORÍA AGÉNTICA HOLÍSTICA (V2 - Costos Desglosados)")
    print("═"*60)

    dataset_path = os.path.join("tests", "data", "golden_dataset.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    graph = await init_graph()
    stats = {
        "success_count": 0,
        "total_steps": 0,
        "total_cost": 0.0,
        "tool_usage_cost": {},
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
        case_cost = 0.0

        async for chunk in graph.astream(input_state, config=config, stream_mode="values"):
            if "messages" in chunk:
                last_msg = chunk["messages"][-1]
                all_messages = chunk["messages"]
                num_steps += 1

                # Tracking de Herramientas y Costos
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        t_name = tc['name']
                        print(f"   [🛠️ TOOL CALL]: {t_name}({tc['args']})")
                        cost = TOOL_COSTS.get(t_name, TOOL_COSTS["default"])
                        case_cost += cost
                        stats["tool_usage_cost"][t_name] = stats["tool_usage_cost"].get(
                            t_name, 0.0) + cost

                elif last_msg.type == "tool":
                    print(f"   [📥 TOOL RES]: {str(last_msg.content)[:100]}...")

                if last_msg.type == "ai" and not last_msg.tool_calls:
                    final_msg = last_msg.content
                    # Costo por respuesta final
                    case_cost += TOOL_COSTS["default"]

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
        stats["total_cost"] += case_cost

        print(
            f"CASE: {case['id']} | Score: {evaluation['score']}/5 | Cost: ${case_cost:.4f} | {'⭐' if is_success else '🔴'}")

    # --- REPORTE DE ALTO NIVEL ---
    success_rate = (stats["success_count"] / len(dataset)) * 100
    print("\n" + "📊 RESUMEN EJECUTIVO")
    print(f"✅ SUCCESS RATE: {success_rate:.1f}%")
    print(f"💰 COSTO TOTAL: ${stats['total_cost']:.4f} USD")
    print("\n🛠️ DESGLOSE DE COSTOS POR HERRAMIENTA:")
    for t, c in sorted(stats["tool_usage_cost"].items(), key=lambda x: x[1], reverse=True):
        print(f"  • {t:25}: ${c:.4f}")

    print("-" * 60)
    if stats["failures"]:
        print("❌ ANÁLISIS DE FALLOS:")
        for f in stats["failures"]:
            print(f"  • {f['id']}: {f['reason'][:100]}...")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_senior_benchmark())
