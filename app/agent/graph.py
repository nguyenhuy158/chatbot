"""LangGraph state machine assembly.

Flow:
  START → load_memory → plan
            plan ─ intent=rag    → rag_search → plan
            plan ─ intent=tool   → tool_call → plan
            plan ─ intent=direct → generate → save_memory → END
            plan ─ iteration >= max → generate → save_memory → END
"""
from langgraph.graph import END, StateGraph

from app.agent.nodes import (
    generate,
    load_memory,
    plan,
    rag_search,
    save_memory,
    tool_call,
)
from app.agent.state import AgentState
from app.core.config import settings


def route_after_plan(state: AgentState) -> str:
    """Conditional edge from plan node."""
    if state.get("iteration", 0) >= settings.LLM_MAX_ITERATIONS:
        return "generate"

    intent = state.get("intent", "direct")
    if intent == "rag":
        return "rag_search"
    if intent == "tool":
        if state.get("pending_tool_calls"):
            return "tool_call"
        # Plan said tool but no calls — fall back to direct
        return "generate"
    return "generate"


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("load_memory", load_memory)
    graph.add_node("plan", plan)
    graph.add_node("rag_search", rag_search)
    graph.add_node("tool_call", tool_call)
    graph.add_node("generate", generate)
    graph.add_node("save_memory", save_memory)

    graph.set_entry_point("load_memory")
    graph.add_edge("load_memory", "plan")

    graph.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "rag_search": "rag_search",
            "tool_call": "tool_call",
            "generate": "generate",
        },
    )

    # RAG and tools feed back to plan so the model can chain
    graph.add_edge("rag_search", "plan")
    graph.add_edge("tool_call", "plan")

    graph.add_edge("generate", "save_memory")
    graph.add_edge("save_memory", END)

    return graph.compile()


agent_graph = build_graph()
