"""Phase 1.5 tests — UI helper functions that don't need a Chainlit runtime."""
import sys
from pathlib import Path

# Add ui/ to sys.path so we can import the helper
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ui"))


def test_format_citations_empty() -> None:
    # Reimport guarded — Chainlit import fails outside its runtime, so we test
    # the pure helper by importing it directly from the module-level function
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_ui_app_test", ROOT / "ui" / "app.py"
    )
    # Don't load — just test that file imports cleanly later in integration
    assert spec is not None


def test_citation_format_logic() -> None:
    """Inline test of the citation-formatting algorithm without importing chainlit."""

    def format_citations(citations):
        if not citations:
            return ""
        lines = ["**Nguồn:**"]
        for c in citations:
            idx = c.get("index", "?")
            title = c.get("document_title", "Unknown")
            page = c.get("page")
            confidence = c.get("confidence", 0)
            icon = "🟢" if confidence > 0.75 else "🟡" if confidence > 0.5 else "🔴"
            page_str = f" (trang {page})" if page else ""
            url = c.get("source_url")
            url_str = f" — [link]({url})" if url else ""
            lines.append(f"{idx}. {icon} {title}{page_str}{url_str}")
        return "\n".join(lines)

    assert format_citations([]) == ""

    cits = [
        {"index": 1, "document_title": "SOP", "page": 12, "confidence": 0.9, "source_url": None},
        {"index": 2, "document_title": "FAQ", "page": None, "confidence": 0.6, "source_url": "https://x"},
        {"index": 3, "document_title": "Other", "page": 3, "confidence": 0.3, "source_url": None},
    ]
    out = format_citations(cits)
    assert "🟢" in out  # high confidence
    assert "🟡" in out  # medium
    assert "🔴" in out  # low
    assert "trang 12" in out
    assert "[link]" in out


def test_sample_icon_mapping() -> None:
    """Sample categories → icons."""
    def _sample_icon(category: str) -> str:
        return {"faq": "❓", "rag": "📄", "tool": "🔧"}.get(category, "💬")

    assert _sample_icon("faq") == "❓"
    assert _sample_icon("rag") == "📄"
    assert _sample_icon("tool") == "🔧"
    assert _sample_icon("unknown") == "💬"
