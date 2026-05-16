"""Web search via Tavily API.

Tavily is purpose-built for AI agents — returns clean snippets + URLs.
Free tier: 1000 searches/month. Paid: $0.005/search.

Tracked separately under `web_search` quota in addition to `tool_calls`.
"""
import time
from uuid import UUID

import httpx
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.services.quota import quota_service
from app.tools.base import Tool, ToolResult

logger = get_logger(__name__)


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Câu query để tìm trên web. Cụ thể, ngắn gọn.", min_length=2, max_length=400)
    max_results: int = Field(5, ge=1, le=10, description="Số kết quả trả về (1-10)")


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Tìm kiếm thông tin trên Internet. Dùng khi user hỏi về tin tức mới, "
        "sự kiện hiện tại, hoặc thông tin Claude không biết. KHÔNG dùng cho "
        "câu hỏi về tài liệu nội bộ — đã có RAG."
    )
    args_schema = WebSearchArgs
    quota_metric = "web_search"

    async def run(self, args: WebSearchArgs, user_id: UUID, tenant_id: UUID) -> ToolResult:
        # Charge dedicated web_search quota in addition to tool_calls
        # (this raises QuotaExceededError on overuse — caller handles)
        from app.core.exceptions import QuotaExceededError
        try:
            # We need to know the role for quota — fetched by caller; here we trust
            # tool_call node already charged tool_calls. For web_search dedicated cap:
            # we conservatively charge against external limits by default.
            pass  # Quota is charged in registry.execute()
        except QuotaExceededError:
            raise

        if not settings.TAVILY_API_KEY:
            return ToolResult(
                success=False,
                output=None,
                error="Tavily API key not configured",
            )

        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.TAVILY_API_KEY,
                        "query": args.query,
                        "max_results": args.max_results,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            duration_ms = int((time.perf_counter() - started) * 1000)
            results = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content", "")[:500],
                    "score": r.get("score"),
                }
                for r in data.get("results", [])
            ]
            output = {
                "answer": data.get("answer"),
                "results": results,
            }
            return ToolResult(
                success=True,
                output=output,
                cost_usd=0.005,  # Tavily basic
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning("web_search_failed", error=str(e), query=args.query[:80])
            return ToolResult(
                success=False,
                output=None,
                error=f"Web search failed: {e}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


web_search_tool = WebSearchTool()
