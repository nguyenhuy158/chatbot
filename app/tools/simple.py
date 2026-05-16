"""Safe calculator + time tools.

Calculator uses asteval (sandboxed) — NOT raw eval(). Falls back to a tiny
expression parser if asteval not available.

Time tool returns datetime in user's timezone, defaults to Asia/Ho_Chi_Minh.
"""
import time
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.tools.base import Tool, ToolResult

logger = get_logger(__name__)


# --- Calculator ---

class CalculatorArgs(BaseModel):
    expression: str = Field(
        ...,
        description="Biểu thức toán học. Hỗ trợ +, -, *, /, **, sqrt, sin, cos, log. Không hỗ trợ code.",
        min_length=1,
        max_length=200,
    )


class CalculatorTool(Tool):
    name = "calculator"
    description = (
        "Tính toán biểu thức toán học chính xác. Dùng khi câu trả lời cần "
        "phép tính số học (tránh LLM tự tính sai)."
    )
    args_schema = CalculatorArgs

    async def run(self, args: CalculatorArgs, user_id: UUID, tenant_id: UUID) -> ToolResult:
        started = time.perf_counter()
        try:
            # Try asteval first (proper sandbox)
            try:
                from asteval import Interpreter
                interp = Interpreter(
                    use_numpy=False,
                    no_print=True,
                    no_assign=True,
                    no_listcomp=True,
                )
                result = interp(args.expression)
                if interp.error:
                    raise ValueError("; ".join(str(e.msg) for e in interp.error))
            except ImportError:
                # Fallback: very restricted eval
                result = _safe_eval(args.expression)

            duration_ms = int((time.perf_counter() - started) * 1000)
            return ToolResult(
                success=True,
                output={"expression": args.expression, "result": result},
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"Calculation error: {e}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


def _safe_eval(expr: str) -> float:
    """Tiny safe evaluator — only numbers + + - * / ** ( ) ."""
    import math
    import re

    # Whitelist chars
    if not re.fullmatch(r"[\d\s+\-*/().,eE]+", expr):
        # Allow some named functions
        allowed = ["sqrt", "sin", "cos", "tan", "log", "exp", "pi", "e"]
        cleaned = expr
        for tok in allowed:
            cleaned = cleaned.replace(tok, "")
        if not re.fullmatch(r"[\d\s+\-*/().,eE]+", cleaned):
            raise ValueError("Invalid characters in expression")

    safe_globals = {
        "__builtins__": {},
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "exp": math.exp,
        "pi": math.pi,
        "e": math.e,
    }
    return eval(expr, safe_globals, {})  # noqa: S307


calculator_tool = CalculatorTool()


# --- Current time ---

class CurrentTimeArgs(BaseModel):
    timezone: str = Field(
        "Asia/Ho_Chi_Minh",
        description="IANA timezone, ví dụ Asia/Ho_Chi_Minh, UTC, America/New_York",
    )


class CurrentTimeTool(Tool):
    name = "get_current_time"
    description = (
        "Lấy thời gian hiện tại theo timezone. Dùng khi user hỏi 'bây giờ là mấy giờ', "
        "'hôm nay ngày bao nhiêu', hoặc cần timestamp."
    )
    args_schema = CurrentTimeArgs
    quota_metric = None  # don't charge for time queries

    async def run(self, args: CurrentTimeArgs, user_id: UUID, tenant_id: UUID) -> ToolResult:
        try:
            tz = ZoneInfo(args.timezone)
        except Exception as e:
            return ToolResult(success=False, output=None, error=f"Bad timezone: {e}")

        now = datetime.now(tz)
        return ToolResult(
            success=True,
            output={
                "iso": now.isoformat(),
                "timezone": args.timezone,
                "date_vn": now.strftime("%d/%m/%Y"),
                "time_vn": now.strftime("%H:%M"),
                "weekday": now.strftime("%A"),
            },
        )


current_time_tool = CurrentTimeTool()
