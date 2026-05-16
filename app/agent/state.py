"""LangGraph agent state."""
from typing import Annotated, Literal, TypedDict
from uuid import UUID

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State passed between LangGraph nodes."""

    tenant_id: UUID
    user_id: UUID
    role: Literal["internal", "external", "admin"]
    lang: str

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages]

    # Memory
    memories: list[dict]

    # RAG
    rag_results: list[dict]
    rag_citations: list[dict]

    # Tools
    pending_tool_calls: list[dict]  # set by plan, consumed by tool_call
    tool_results: list[dict]  # accumulated

    # Output
    final_answer: str

    # Flow control
    intent: str  # rag | tool | direct
    iteration: int

    # Metadata
    metadata: dict
