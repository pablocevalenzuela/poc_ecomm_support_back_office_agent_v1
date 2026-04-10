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
    """Llamada al LLM-as-a-Judge para calificar la efectividad."""
    prompt = f"""
    Actúa como un Evaluador de Calidad Senior para Asistentes de IA.
    
    PREGUNTA DEL USUARIO: {query}
    RESPUESTA DEL AGENTE: {response}
    RÚBRICA DE ÉXITO: {rubric}
    
    Califica la respuesta del 1 al 5 y da una breve justificación:
    1: Respuesta errónea o peligrosa.
    3: Respuesta correcta pero incompleta.
    5: Respuesta perfecta, cumple con la rúbrica al 100%.
    
    Devuelve solo un JSON con las claves 'score' (int) y 'reason' (str).
    Ejemplo de salida: {{"score": 5, "reason": "La respuesta es precisa..."}}
    """

    try:
        judge_res = await judge_llm.ainvoke(prompt)
        # Extraemos el JSON del contenido
        content = judge_res.content.replace(
            "```json", "").replace("```", "").strip()
        # En algunos modelos HF, la respuesta puede traer texto extra, buscamos el primer { y el último }
        start = content.find("{")
        end = content.rfind("}") + 1
        return json.loads(content[start:end])
    except Exception as e:
        return {"score": 0, "reason": f"Error en el juicio: {str(e)}"}


async def run_senior_benchmark():
    print("🚀 INICIANDO SENIOR AGENT BENCHMARK (HF-as-a-Judge)...")

    # Cargar dataset
    dataset_path = os.path.join("tests", "data", "golden_dataset.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    graph = await init_graph()
    total_score = 0
    results = []

    for case in dataset:
        print(f"\n--- EVALUANDO CASO: {case['id']} ---")
        start_time = time.time()

        config = {"configurable": {"thread_id": f"bench_{int(time.time())}"}}
        input_state = {"messages": [HumanMessage(content=case["input"])]}

        # 1. Ejecutar el Agente REAL
        response = await graph.ainvoke(input_state, config=config)
        final_msg = response["messages"][-1].content
        latency = time.time() - start_time

        # 2. Evaluar Trayectoria: ¿Se usó la herramienta esperada?
        used_tools = [m.tool_calls[0]['name'] for m in response['messages'] if hasattr(
            m, 'tool_calls') and m.tool_calls]
        tool_ok = case['expected_tool'] in used_tools

        # 3. Evaluar Calidad Semántica (Juez HF)
        evaluation = await judge_response(case["input"], final_msg, case["rubric"])

        # 4. Resultados
        print(f"Puntaje Juez: {evaluation['score']}/5")
        print(f"Herramienta OK: {'✅' if tool_ok else '❌'}")
        print(f"Latencia: {latency:.2f}s")
        print(f"Justificación: {evaluation['reason']}")

        total_score += evaluation['score']
        results.append(evaluation)

    avg_score = total_score / len(dataset)
    print("\n" + "="*50)
    print("📊 REPORTE DE CALIDAD FINAL (AI-AUDIT via Hugging Face)")
    print(f"Calidad Promedio: {avg_score:.1f}/5.0")
    print(f"Casos evaluados: {len(dataset)}")
    print(f"Sugerencia: Revisa tu Dashboard de LangSmith para ver los tokens y costos exactos.")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(run_senior_benchmark())
