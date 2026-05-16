"""Phase 8 unit tests — email formatting (no SMTP, no DB)."""
from app.analytics.email_reporter import format_daily_cost_email


def test_format_daily_cost_email_with_traffic() -> None:
    report = {
        "day": "2026-05-13",
        "summary": {
            "messages": 1234,
            "tokens": 5678901,
            "cost_usd": 12.3456,
            "cached": 246,
        },
        "by_model": [
            {"model": "claude-haiku-4-5", "message_count": 800, "cost_usd": 8.0},
            {"model": "gemini-2.5-flash", "message_count": 434, "cost_usd": 4.3456},
        ],
        "csat": {"up": 50, "down": 5, "csat": 0.909},
    }
    msg = format_daily_cost_email(report)
    assert "2026-05-13" in msg.subject
    assert "12.3456" in msg.subject
    assert "1,234" in msg.body_text
    assert "👍 50" in msg.body_text
    assert "claude-haiku-4-5" in msg.body_html
    assert "gemini-2.5-flash" in msg.body_html


def test_format_daily_cost_email_no_traffic() -> None:
    report = {
        "day": "2026-05-13",
        "summary": {"messages": 0, "tokens": 0, "cost_usd": 0, "cached": 0},
        "by_model": [],
        "csat": {"up": 0, "down": 0, "csat": None},
    }
    msg = format_daily_cost_email(report)
    # Should not crash, should say no traffic
    assert "no traffic today" in msg.body_text or "no traffic today" in msg.body_html


def test_format_daily_cost_email_handles_missing_keys() -> None:
    report = {"day": "2026-05-13", "summary": {}, "by_model": [], "csat": {}}
    msg = format_daily_cost_email(report)
    assert "2026-05-13" in msg.subject


def test_format_daily_cost_email_cache_percent() -> None:
    report = {
        "day": "2026-05-13",
        "summary": {"messages": 100, "tokens": 1000, "cost_usd": 1.0, "cached": 30},
        "by_model": [],
        "csat": {"up": 0, "down": 0, "csat": None},
    }
    msg = format_daily_cost_email(report)
    assert "30%" in msg.body_text  # 30 / 100
