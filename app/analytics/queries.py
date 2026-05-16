"""Analytics query service — read the views, return typed dicts.

These power admin endpoints and the daily cost email. Metabase queries
the same views directly via its Postgres connection.
"""
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


async def dau_last_n_days(db: AsyncSession, tenant_id: UUID, days: int = 30) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT day, dau, user_messages, bot_messages
            FROM v_daily_active_users
            WHERE tenant_id = :tenant_id
              AND day >= CURRENT_DATE - (:days || ' days')::interval
            ORDER BY day DESC
            """
        ),
        {"tenant_id": str(tenant_id), "days": days},
    )
    return [dict(r) for r in result.mappings().all()]


async def cost_summary(db: AsyncSession, tenant_id: UUID, days: int = 30) -> dict:
    """Aggregate cost summary for the last N days."""
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(DISTINCT day) AS days_active,
                COALESCE(SUM(message_count), 0) AS total_messages,
                COALESCE(SUM(tokens_in), 0) AS total_tokens_in,
                COALESCE(SUM(tokens_out), 0) AS total_tokens_out,
                COALESCE(SUM(cost_usd), 0)::numeric(10,4) AS total_cost_usd,
                COALESCE(SUM(cached_responses), 0) AS cached_responses
            FROM v_cost_per_day
            WHERE tenant_id = :tenant_id
              AND day >= CURRENT_DATE - (:days || ' days')::interval
            """
        ),
        {"tenant_id": str(tenant_id), "days": days},
    )
    row = result.mappings().first()
    return dict(row) if row else {}


async def cost_by_day(db: AsyncSession, tenant_id: UUID, days: int = 14) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT day, model, message_count, tokens_in, tokens_out, cost_usd, cached_responses
            FROM v_cost_per_day
            WHERE tenant_id = :tenant_id
              AND day >= CURRENT_DATE - (:days || ' days')::interval
            ORDER BY day DESC, cost_usd DESC
            """
        ),
        {"tenant_id": str(tenant_id), "days": days},
    )
    return [dict(r) for r in result.mappings().all()]


async def top_users_by_cost(db: AsyncSession, tenant_id: UUID, limit: int = 20) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT email, role, message_count, total_tokens, total_cost_usd, last_message_at
            FROM v_cost_per_user
            WHERE tenant_id = :tenant_id
            ORDER BY total_cost_usd DESC NULLS LAST
            LIMIT :limit
            """
        ),
        {"tenant_id": str(tenant_id), "limit": limit},
    )
    return [dict(r) for r in result.mappings().all()]


async def csat_weekly(db: AsyncSession, tenant_id: UUID, weeks: int = 12) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT week, total_feedback, thumbs_up, thumbs_down, csat
            FROM v_csat
            WHERE tenant_id = :tenant_id
              AND week >= DATE_TRUNC('week', CURRENT_DATE - (:weeks || ' weeks')::interval)
            ORDER BY week DESC
            """
        ),
        {"tenant_id": str(tenant_id), "weeks": weeks},
    )
    return [dict(r) for r in result.mappings().all()]


async def channel_breakdown(db: AsyncSession, tenant_id: UUID) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT channel, conversations, unique_users, messages
            FROM v_channel_breakdown
            WHERE tenant_id = :tenant_id
            ORDER BY messages DESC
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    return [dict(r) for r in result.mappings().all()]


async def tool_usage(db: AsyncSession, tenant_id: UUID, days: int = 7) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT day, tool_name,
                   SUM(calls) AS calls,
                   SUM(successful) AS successful,
                   SUM(failed) AS failed,
                   ROUND(AVG(avg_duration_ms)::numeric, 0) AS avg_duration_ms
            FROM v_tool_usage
            WHERE tenant_id = :tenant_id
              AND day >= CURRENT_DATE - (:days || ' days')::interval
            GROUP BY day, tool_name
            ORDER BY day DESC, calls DESC
            """
        ),
        {"tenant_id": str(tenant_id), "days": days},
    )
    return [dict(r) for r in result.mappings().all()]


async def funnel(db: AsyncSession, tenant_id: UUID) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT cohort, signed_up, sent_first_message, sent_second_message, retained_7d
            FROM v_funnel_signup_to_active
            WHERE tenant_id = :tenant_id
            ORDER BY cohort DESC
            """
        ),
        {"tenant_id": str(tenant_id)},
    )
    return [dict(r) for r in result.mappings().all()]


async def moderation_summary(db: AsyncSession, tenant_id: UUID, days: int = 30) -> list[dict]:
    result = await db.execute(
        text(
            """
            SELECT day, event_type, severity, action_taken, events
            FROM v_moderation_summary
            WHERE tenant_id = :tenant_id
              AND day >= CURRENT_DATE - (:days || ' days')::interval
            ORDER BY day DESC, events DESC
            """
        ),
        {"tenant_id": str(tenant_id), "days": days},
    )
    return [dict(r) for r in result.mappings().all()]


async def daily_cost_report(db: AsyncSession, tenant_id: UUID, day: date | None = None) -> dict:
    """Build a single-day cost report for email."""
    day = day or (date.today() - timedelta(days=1))

    result = await db.execute(
        text(
            """
            SELECT
                COALESCE(SUM(message_count), 0) AS messages,
                COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens,
                COALESCE(SUM(cost_usd), 0)::numeric(10,4) AS cost_usd,
                COALESCE(SUM(cached_responses), 0) AS cached
            FROM v_cost_per_day
            WHERE tenant_id = :tenant_id AND day = :day
            """
        ),
        {"tenant_id": str(tenant_id), "day": day},
    )
    summary = dict(result.mappings().first() or {})

    # By model
    by_model_result = await db.execute(
        text(
            """
            SELECT model, message_count, cost_usd::numeric(10,4) AS cost_usd
            FROM v_cost_per_day
            WHERE tenant_id = :tenant_id AND day = :day
            ORDER BY cost_usd DESC
            """
        ),
        {"tenant_id": str(tenant_id), "day": day},
    )
    by_model = [dict(r) for r in by_model_result.mappings().all()]

    # CSAT today
    csat_result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (WHERE rating = 1) AS up,
                COUNT(*) FILTER (WHERE rating = -1) AS down
            FROM feedback
            WHERE tenant_id = :tenant_id
              AND DATE(created_at AT TIME ZONE 'Asia/Ho_Chi_Minh') = :day
            """
        ),
        {"tenant_id": str(tenant_id), "day": day},
    )
    csat = dict(csat_result.mappings().first() or {})
    total_fb = (csat.get("up", 0) or 0) + (csat.get("down", 0) or 0)
    csat["csat"] = round(csat.get("up", 0) / total_fb, 3) if total_fb else None

    return {"day": day.isoformat(), "summary": summary, "by_model": by_model, "csat": csat}
