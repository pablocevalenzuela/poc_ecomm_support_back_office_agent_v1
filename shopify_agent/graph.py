from langgraph.graph import StateGraph, END
from .state import AgentState
from .tools import tools

def call_model(state: AgentState):
    # Lógica de invocación al LLM aquí
    return state

workflow = StateGraph(AgentState)
workflow.add_node("agent", call_model)
workflow.set_entry_point("agent")
workflow.add_edge("agent", END)

graph = workflow.compile()
