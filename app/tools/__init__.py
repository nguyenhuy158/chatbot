"""Tools module — function-calling tools for the agent."""
from app.tools.base import Tool, ToolResult
from app.tools.registry import (
    ALL_TOOLS,
    execute_tool,
    get_tool_specs_for_llm,
    get_tools_for_role,
)

__all__ = [
    "Tool",
    "ToolResult",
    "ALL_TOOLS",
    "execute_tool",
    "get_tool_specs_for_llm",
    "get_tools_for_role",
]
