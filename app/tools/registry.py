"""Tool registry — central place to look up, filter by role, execute with audit.

Execution wraps:
  - Role check
  - Quota check (dedicated metric if any + tool_calls)
  - Run the tool
  - Persist tool_audit row
  - Return ToolResult
"""
import json
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger
from app.services.quota import quota_service
from app.tools.base import Tool, ToolResult
from app.tools.simple import calculator_tool, current_time_tool
from app.tools.web_fetch import web_fetch_tool
from app.tools.web_search import web_search_tool

logger = get_logger(__name__)


# Register all available tools here
ALL_TOOLS: dict[str, Tool] = {
    t.name: t for t in [
        web_search_tool,
        web_fetch_tool,
        calculator_tool,
        current_time_tool,
    ]
}


def get_tools_for_role(role: str) -> list[Tool]:
    """Return tools the role is allowed to invoke."""
    return [t for t in ALL_TOOLS.values() if role in t.allowed_roles]


def get_tool_specs_for_llm(role: str) -> list[dict]:
    """LLM-ready function-calling spec list."""
    return [t.to_function_spec() for t in get_tools_for_role(role)]


async def execute_tool(
    db: AsyncSession,
    tool_name: str,
    raw_args: dict,
    user_id: UUID,
    tenant_id: UUID,
    role: str,
) -> ToolResult:
    """Run a tool by name with role check + quota + audit log.

    Raises ForbiddenError if role not allowed.
    Raises QuotaExceededError if user is out of quota.
    Returns ToolResult on success or controlled failure.
    """
    tool = ALL_TOOLS.get(tool_name)
    if not tool:
        return ToolResult(success=False, output=None, error=f"Unknown tool: {tool_name}")

    if role not in tool.allowed_roles:
        raise ForbiddenError(f"Role '{role}' may not use tool '{tool_name}'")

    # Validate args
    try:
        args = tool.args_schema(**raw_args)
    except ValidationError as e:
        return ToolResult(success=False, output=None, error=f"Invalid args: {e.errors()}")

    # Charge quotas: tool_calls always, dedicated metric if any
    await quota_service.check_and_reserve(
        user_id=user_id, role=role, metric="tool_calls", amount=1
    )
    if tool.quota_metric and tool.quota_metric != "tool_calls":
        await quota_service.check_and_reserve(
            user_id=user_id, role=role, metric=tool.quota_metric, amount=1
        )

    # Execute
    result = await tool.run(args, user_id=user_id, tenant_id=tenant_id)

    # Audit (best-effort — failure to audit shouldn't break the call)
    try:
        await _audit_log(
            db=db,
            tenant_id=tenant_id,
            user_id=user_id,
            tool_name=tool_name,
            args=raw_args,
            result=result,
        )
    except Exception as e:
        logger.warning("tool_audit_failed", error=str(e), tool=tool_name)

    return result


async def _audit_log(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    tool_name: str,
    args: dict,
    result: ToolResult,
) -> None:
    """Append to tool_audit table."""
    # Redact long outputs
    output_for_log = result.output
    if isinstance(output_for_log, dict):
        # Keep but truncate long strings
        output_for_log = _truncate_nested(output_for_log, 1000)

    await db.execute(
        text(
            """
            INSERT INTO tool_audit
                (id, tenant_id, user_id, tool_name, input, output, success, error, duration_ms, created_at)
            VALUES
                (:id, :tenant_id, :user_id, :tool_name, CAST(:input AS jsonb),
                 CAST(:output AS jsonb), :success, :error, :duration_ms, NOW())
            """
        ),
        {
            "id": str(uuid4()),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "tool_name": tool_name,
            "input": json.dumps(args, default=str),
            "output": json.dumps(output_for_log, default=str) if output_for_log else None,
            "success": result.success,
            "error": result.error,
            "duration_ms": result.duration_ms,
        },
    )


def _truncate_nested(obj, max_len: int):
    """Truncate strings in nested dict/list for audit log readability."""
    if isinstance(obj, str):
        return obj[:max_len] + ("..." if len(obj) > max_len else "")
    if isinstance(obj, dict):
        return {k: _truncate_nested(v, max_len) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_nested(v, max_len) for v in obj]
    return obj
