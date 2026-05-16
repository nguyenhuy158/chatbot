"""Reputation score and ban management.

Score starts at 100. Moderation events decrement based on severity.
Below 30 → automatic temp ban (24h). Manual review required for permanent ban.

Score recovers slowly: +5 per day of clean activity (cron job, not implemented yet).
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger
from app.db.models import User

logger = get_logger(__name__)


# Score deductions per moderation event severity
SEVERITY_PENALTY = {
    "low": 0,
    "med": 5,
    "high": 20,
}

# Score thresholds
WARN_THRESHOLD = 70
TEMP_BAN_THRESHOLD = 30
PERMA_BAN_REVIEW_THRESHOLD = 10

# Temp ban duration in hours, escalates with repeat offenses
TEMP_BAN_HOURS = {
    1: 1,  # first temp ban: 1h
    2: 24,  # second: 24h
    3: 168,  # third: 7d
}


async def get_user(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def check_banned(db: AsyncSession, user_id: UUID, tenant_id: UUID) -> None:
    """Raise ForbiddenError if user is currently banned. Call early in request lifecycle."""
    user = await get_user(db, user_id, tenant_id)
    if not user:
        return
    if user.banned_until and user.banned_until > datetime.now(timezone.utc):
        remaining_hours = int(
            (user.banned_until - datetime.now(timezone.utc)).total_seconds() / 3600
        )
        raise ForbiddenError(
            f"Bạn đang bị tạm khóa do vi phạm. Còn {remaining_hours} giờ.",
            banned_until=user.banned_until.isoformat(),
        )


async def penalize(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: UUID,
    severity: str,
    reason: str,
) -> User | None:
    """Apply a moderation penalty. Updates score, may issue temp ban.

    Returns updated User (or None if not found).
    """
    user = await get_user(db, user_id, tenant_id)
    if not user:
        return None

    penalty = SEVERITY_PENALTY.get(severity, 0)
    if penalty == 0:
        return user

    user.reputation_score = max(0, user.reputation_score - penalty)
    logger.info(
        "reputation_penalized",
        user_id=str(user_id),
        new_score=user.reputation_score,
        severity=severity,
        reason=reason,
    )

    # Auto-ban if below temp threshold
    if user.reputation_score < TEMP_BAN_THRESHOLD:
        # Count prior bans (rough heuristic — last 30 days)
        prior_bans = 1  # TODO: query moderation_events to count
        hours = TEMP_BAN_HOURS.get(prior_bans, 168)
        user.banned_until = datetime.now(timezone.utc) + timedelta(hours=hours)
        logger.warning(
            "user_temp_banned",
            user_id=str(user_id),
            hours=hours,
            score=user.reputation_score,
        )

    await db.flush()
    return user


async def record_moderation_event(
    db: AsyncSession,
    tenant_id: UUID,
    user_id: UUID,
    event_type: str,
    severity: str,
    content_snippet: str,
    action_taken: str,
) -> None:
    """Append to moderation_events table for audit."""
    from sqlalchemy import text

    await db.execute(
        text(
            """
            INSERT INTO moderation_events
                (id, tenant_id, user_id, event_type, severity, content_snippet, action_taken, created_at)
            VALUES
                (gen_random_uuid(), :tenant_id, :user_id, :event_type, :severity, :snippet, :action, NOW())
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "event_type": event_type,
            "severity": severity,
            "snippet": content_snippet[:500],
            "action": action_taken,
        },
    )


async def admin_unban(
    db: AsyncSession, user_id: UUID, tenant_id: UUID, reset_score: bool = False
) -> User | None:
    """Admin lifts ban manually."""
    user = await get_user(db, user_id, tenant_id)
    if not user:
        return None
    user.banned_until = None
    if reset_score:
        user.reputation_score = 100
    await db.flush()
    return user
