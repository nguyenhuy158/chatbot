"""Quota enforcement with Redis counters.

Per-user, per-day, per-metric counters. Hard block at 100%, soft warn at 80%.
Keys: quota:{user_id}:{YYYY-MM-DD}:{metric}
TTL: until 00:00 GMT+7 next day

Metrics tracked:
  - messages: count of user-initiated chat requests
  - tokens: cumulative LLM tokens (in + out)
  - cost: cumulative USD cents
  - web_search: tool calls to web_search
  - tool_calls: total tool calls
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import QuotaExceededError
from app.core.logging import get_logger

logger = get_logger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

Metric = Literal["messages", "tokens", "cost_cents", "web_search", "tool_calls"]


@dataclass
class QuotaStatus:
    used: int
    limit: int
    remaining: int
    percent: float
    warned: bool  # crossed 80%
    blocked: bool  # crossed 100%


def _today_key() -> str:
    """Date in GMT+7 — quotas reset at 00:00 VN time."""
    return datetime.now(VN_TZ).strftime("%Y-%m-%d")


def _seconds_until_midnight_vn() -> int:
    now = datetime.now(VN_TZ)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())


def _quota_key(user_id: UUID, metric: Metric) -> str:
    return f"quota:{user_id}:{_today_key()}:{metric}"


def get_limits(role: str) -> dict[str, int]:
    """Per-role daily limits."""
    if role in ("internal", "admin"):
        return {
            "messages": settings.QUOTA_INTERNAL_MESSAGES,
            "tokens": settings.QUOTA_INTERNAL_TOKENS,
            "cost_cents": int(settings.QUOTA_INTERNAL_COST_USD * 100),
            "web_search": 50,
            "tool_calls": 200,
        }
    return {
        "messages": settings.QUOTA_EXTERNAL_MESSAGES,
        "tokens": settings.QUOTA_EXTERNAL_TOKENS,
        "cost_cents": int(settings.QUOTA_EXTERNAL_COST_USD * 100),
        "web_search": 10,
        "tool_calls": 20,
    }


class QuotaService:
    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def get_status(
        self, user_id: UUID, role: str, metric: Metric
    ) -> QuotaStatus:
        r = await self._get_redis()
        key = _quota_key(user_id, metric)
        used_str = await r.get(key)
        used = int(used_str) if used_str else 0
        limit = get_limits(role)[metric]
        remaining = max(0, limit - used)
        percent = (used / limit * 100) if limit > 0 else 0
        return QuotaStatus(
            used=used,
            limit=limit,
            remaining=remaining,
            percent=percent,
            warned=percent >= 80,
            blocked=used >= limit,
        )

    async def get_all(self, user_id: UUID, role: str) -> dict[str, QuotaStatus]:
        """Snapshot of all metrics for the user. Used by /api/me/quota."""
        result: dict[str, QuotaStatus] = {}
        for metric in get_limits(role).keys():
            result[metric] = await self.get_status(user_id, role, metric)  # type: ignore[arg-type]
        return result

    async def check_and_reserve(
        self,
        user_id: UUID,
        role: str,
        metric: Metric,
        amount: int = 1,
    ) -> QuotaStatus:
        """Atomically check + increment. Raises QuotaExceededError if would exceed.

        Uses Redis INCRBY which is atomic. We check after increment and rollback if needed.
        Race-safe enough for our scale (1k req/day).
        """
        r = await self._get_redis()
        key = _quota_key(user_id, metric)
        limit = get_limits(role)[metric]

        # Atomic increment
        new_used = await r.incrby(key, amount)

        # Set expiry on first use
        if new_used == amount:
            await r.expire(key, _seconds_until_midnight_vn())

        if new_used > limit:
            # Rollback
            await r.decrby(key, amount)
            raise QuotaExceededError(
                f"Daily {metric} quota exceeded ({limit} per day)",
                metric=metric,
                limit=limit,
                resets_at=_seconds_until_midnight_vn(),
            )

        status = QuotaStatus(
            used=new_used,
            limit=limit,
            remaining=max(0, limit - new_used),
            percent=(new_used / limit * 100) if limit > 0 else 0,
            warned=new_used >= limit * 0.8,
            blocked=new_used >= limit,
        )

        if status.warned and not (new_used - amount) >= limit * 0.8:
            # Just crossed 80% threshold
            logger.info("quota_warning", user_id=str(user_id), metric=metric, percent=status.percent)

        return status

    async def add(
        self,
        user_id: UUID,
        role: str,
        metric: Metric,
        amount: int,
    ) -> None:
        """Increment a counter without limit check.

        Used for after-the-fact accounting (tokens, cost — we don't know exact
        amount until the LLM call completes). If this pushes over the limit,
        next call to check_and_reserve will block.
        """
        if amount <= 0:
            return
        r = await self._get_redis()
        key = _quota_key(user_id, metric)
        new_used = await r.incrby(key, amount)
        if new_used == amount:
            await r.expire(key, _seconds_until_midnight_vn())

    async def reset(self, user_id: UUID, metric: Metric | None = None) -> None:
        """Admin: reset quota for a user. Useful for support."""
        r = await self._get_redis()
        if metric:
            await r.delete(_quota_key(user_id, metric))
        else:
            for m in ["messages", "tokens", "cost_cents", "web_search", "tool_calls"]:
                await r.delete(_quota_key(user_id, m))  # type: ignore[arg-type]


quota_service = QuotaService()
