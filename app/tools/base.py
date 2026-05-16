"""Base class for tools — typed input/output + metadata for LLM function calling.

A Tool is:
  - name: stable identifier the LLM will use to call it
  - description: prompt-visible explanation of when to use it
  - args_schema: Pydantic model for typed arguments
  - allowed_roles: which user roles can invoke this tool
  - quota_metric: which quota counter to charge against
  - run(): the actual implementation
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar
from uuid import UUID

from pydantic import BaseModel

from app.services.quota import Metric


@dataclass
class ToolResult:
    success: bool
    output: Any
    error: str | None = None
    cost_usd: float = 0.0
    duration_ms: int = 0


class Tool(ABC):
    """Subclass and implement `run`. Class variables define metadata."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_schema: ClassVar[type[BaseModel]]
    allowed_roles: ClassVar[set[str]] = {"internal", "external", "admin"}
    quota_metric: ClassVar[Metric | None] = "tool_calls"

    @abstractmethod
    async def run(self, args: BaseModel, user_id: UUID, tenant_id: UUID) -> ToolResult: ...

    def to_function_spec(self) -> dict:
        """Render as OpenAI/Anthropic function-calling spec for the LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.args_schema.model_json_schema(),
        }
