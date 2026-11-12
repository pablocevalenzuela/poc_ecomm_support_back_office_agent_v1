from shopify_agent.graph import workflow


def main():
    # 1. Compilamos el flujo en memoria SIN checkpointer (no requiere PostgreSQL)
    graph = workflow.compile()

    # 2. Obtenemos los bytes de la imagen generada por LangGraph
    png_bytes = graph.get_graph().draw_mermaid_png()

    # Escribimos el archivo PNG en disco
    with open("mi_grafo_langgraph.png", "wb") as f:
        f.write(png_bytes)
    print("¡Grafo exportado nativamente como 'mi_grafo_langgraph.png'!")


if __name__ == "__main__":
    main()
