"""Fetch a single URL and return cleaned content.

Use sparingly — many sites block bots or have huge pages.
Cap content at 50KB to avoid blowing the context window.
"""
import time
from uuid import UUID

import httpx
from pydantic import BaseModel, Field, HttpUrl

from app.core.logging import get_logger
from app.tools.base import Tool, ToolResult

logger = get_logger(__name__)

MAX_BYTES = 50_000


class WebFetchArgs(BaseModel):
    url: HttpUrl = Field(..., description="URL đầy đủ (https://...)")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = (
        "Tải nội dung 1 URL đã biết. Dùng SAU web_search khi cần đọc chi tiết "
        "1 trang. Không dùng cho URL chưa biết — query web_search trước."
    )
    args_schema = WebFetchArgs

    async def run(self, args: WebFetchArgs, user_id: UUID, tenant_id: UUID) -> ToolResult:
        started = time.perf_counter()
        url = str(args.url)
        try:
            async with httpx.AsyncClient(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "ChatbotAgent/1.0"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text" not in content_type and "html" not in content_type:
                    return ToolResult(
                        success=False,
                        output=None,
                        error=f"Unsupported content-type: {content_type}",
                    )
                # Cap size
                content = resp.text[:MAX_BYTES]

            # Strip HTML to text
            text = _strip_html(content)
            duration_ms = int((time.perf_counter() - started) * 1000)
            return ToolResult(
                success=True,
                output={
                    "url": url,
                    "content": text[:MAX_BYTES],
                    "truncated": len(content) >= MAX_BYTES,
                },
                duration_ms=duration_ms,
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"HTTP {e.response.status_code}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as e:
            logger.warning("web_fetch_failed", url=url, error=str(e))
            return ToolResult(
                success=False,
                output=None,
                error=f"Fetch failed: {e}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


def _strip_html(html: str) -> str:
    """Naive HTML → text. Good enough for an agent; not for production scraping."""
    import re

    # Remove script + style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return text.strip()


web_fetch_tool = WebFetchTool()
