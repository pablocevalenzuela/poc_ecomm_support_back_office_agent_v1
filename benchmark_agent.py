import asyncio
import json
import os
import time
from shopify_agent.graph import init_graph
from shopify_agent.settings import settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

# CONFIGURACIÓN DEL JUEZ (Hugging Face)
# Usamos un modelo 70B para asegurar un juicio de alta calidad
judge_llm_hf = HuggingFaceEndpoint(
    repo_id="Qwen/Qwen2.5-72B-Instruct",
    task="chat-completion",
    huggingfacehub_api_token=settings.huggingface_api_token,
    temperature=0.01,
)
judge_llm = ChatHuggingFace(llm=judge_llm_hf)


async def judge_response(query, response, rubric):
    """Llamada al LLM-as-a-Judge para calificar la efectividad holística."""
    prompt = f"""
    Actúa como un Auditor de IA Senior especializado en Sistemas Agénticos.
    
    CONTEXTO DE AUDITORÍA:
    - PREGUNTA: {query}
    - RESPUESTA: {response}
    - REQUISITOS (RÚBRICA): {rubric}
    
    CRITERIOS DE PENALIZACIÓN CRÍTICA:
    1. TRANSPARENCIA: Si la respuesta no menciona o no da a entender que se consultó un sistema real (Shopify, Catálogo), califica máximo con 3.
    2. PRECISIÓN: Si omite datos clave presentes en la rúbrica (SKUs, nombres exactos, iconos de estado), califica máximo con 3.
    3. ALUCINACIÓN: Si la respuesta contradice la lógica de la herramienta, califica con 1.

    PUNTUACIÓN:
    1: Falla crítica o respuesta peligrosa.
    3: Correcta técnicamente pero "Caja Negra" (no menciona la fuente) o incompleta.
    5: Respuesta Perfecta: Precisa, amable y transparente sobre el uso de herramientas.
    
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
    print("🚀 AUDITORÍA AGÉNTICA HOLÍSTICA")
    print("═"*60)

    dataset_path = os.path.join("tests", "data", "golden_dataset.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    graph = await init_graph()
    stats = {
        "success_count": 0,
        "total_steps": 0,
        "total_cost": 0.0,
        "failures": []
    }

    # Precios Ref: Claude 3.5 Sonnet ($3/M In, $15/M Out)
    COST_PER_STEP_EST = 0.002  # Aprox $0.002 USD por paso en promedio

    for case in dataset:
        print(f"\n🔍 EVALUANDO: {case['id']}")
        start_time = time.time()
        
        # Configuración con METADATOS para LangSmith
        config = {
            "configurable": {"thread_id": f"bench_{int(time.time())}"},
            "metadata": {
                "run_type": "benchmark_holistico",
                "case_id": case["id"],
                "evaluator": "Qwen-72B-Judge"
            }
        }
        input_state = {"messages": [HumanMessage(content=case["input"])]}

        # --- STREAMING PARA OBSERVABILIDAD ReAct ---
        final_msg = ""
        num_steps = 0
        all_messages = []
        
        async for chunk in graph.astream(input_state, config=config, stream_mode="values"):
            if "messages" in chunk:
                last_msg = chunk["messages"][-1]
                all_messages = chunk["messages"] # Mantener lista completa para validación
                num_steps += 1
                
                # Mostrar Razonamiento (AI Message con Tool Calls)
                if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
                    for tc in last_msg.tool_calls:
                        print(f"   [🛠️ TOOL CALL]: {tc['name']}({tc['args']})")
                
                # Mostrar Resultado de Herramienta (Tool Message)
                elif last_msg.type == "tool":
                    print(f"   [📥 TOOL RES]: {str(last_msg.content)[:100]}...")
                
                # Guardar respuesta final
                if last_msg.type == "ai" and not last_msg.tool_calls:
                    final_msg = last_msg.content

        latency = time.time() - start_time

        # 2. Validación de Herramientas
        used_tools = [m.tool_calls[0]['name'] for m in all_messages if hasattr(m, 'tool_calls') and m.tool_calls]
        tool_ok = case['expected_tool'] in used_tools

        # 3. Juicio Semántico
        evaluation = await judge_response(case["input"], final_msg, case["rubric"])

        # 4. Success Criteria (Score >= 4 y Tool OK)
        is_success = evaluation['score'] >= 4 and tool_ok
        if is_success:
            stats["success_count"] += 1
        else:
            stats["failures"].append(
                {"id": case["id"], "reason": evaluation["reason"]})

        stats["total_steps"] += num_steps
        stats["total_cost"] += (num_steps * COST_PER_STEP_EST)

        print(f"CASE: {case['id']} | Score: {evaluation['score']}/5 | Steps: {num_steps} | Tool: {'✅' if tool_ok else '❌'} | {'⭐' if is_success else '🔴'}")

    # --- REPORTE DE ALTO NIVEL ---
    success_rate = (stats["success_count"] / len(dataset)) * 100
    avg_steps = stats["total_steps"] / len(dataset)

    print("\n" + "📊 RESUMEN EJECUTIVO")
    print(f"✅ SUCCESS RATE: {success_rate:.1f}%")
    print(f"🛤️ EFICIENCIA PROM: {avg_steps:.1f} pasos/tarea")
    print(f"💰 COSTO ESTIMADO: ${stats['total_cost']:.4f} USD")
    print("-" * 60)

    if stats["failures"]:
        print("❌ ANÁLISIS DE FALLOS (Bloqueos para el 100%):")
        for f in stats["failures"]:
            print(f"  • {f['id']}: {f['reason'][:100]}...")

    print("-" * 60)
    print("💡 PRÓXIMOS PASOS (Best Practices):")
    print("  1. System 2 Thinking: Añade un paso de 'Reflexión' para casos de Stock.")
    print("  2. Few-Shot: Inyecta ejemplos de éxito en el System Prompt para reducir pasos.")
    print("  3. Token ROI: Si pasos > 5, considera resumir el historial de mensajes.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_senior_benchmark())
