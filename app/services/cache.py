"""L1 exact-match cache for chat responses.

Key: SHA-256 of (query + role + user_lang) — role is included so internal
context never bleeds into external. user_id is NOT included because that
defeats the purpose of caching.

Cache only DETERMINISTIC, KNOWLEDGE-style queries. Skip if:
  - Query contains personal pronouns ("tôi", "my", "của tôi")
  - Memory context was used (would change answer per-user)
  - Tools were called (results are time-sensitive)

This is best-effort — wrong cache hit = inconvenient but not dangerous because
role-scoped key prevents leakage across permission boundaries.
"""
import hashlib
import json
import re
from dataclasses import dataclass

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


PERSONAL_INDICATORS = re.compile(
    r"\b(tôi|của tôi|mình|của mình|my|i'm|i am|cá nhân|ngày sinh|email của)\b",
    re.IGNORECASE,
)


@dataclass
class CachedResponse:
    answer: str
    citations: list[dict]
    model: str
    cached_at: int  # unix ts


def is_cacheable(query: str, used_memory: bool, used_tools: bool) -> bool:
    """Decide if a query is safe to cache."""
    if used_memory or used_tools:
        return False
    if PERSONAL_INDICATORS.search(query):
        return False
    if len(query.strip()) < 5:
        return False
    return True


def make_key(query: str, role: str, lang: str) -> str:
    """Stable cache key. Normalizes query (lowercase, strip)."""
    normalized = query.strip().lower()
    raw = f"{role}|{lang}|{normalized}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"cache:l1:{digest}"


class L1Cache:
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

    async def get(self, query: str, role: str, lang: str) -> CachedResponse | None:
        r = await self._get_redis()
        key = make_key(query, role, lang)
        raw = await r.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return CachedResponse(
                answer=data["answer"],
                citations=data.get("citations", []),
                model=data.get("model", "unknown"),
                cached_at=data.get("cached_at", 0),
            )
        except Exception as e:
            logger.warning("cache_corrupt", key=key, error=str(e))
            return None

    async def set(
        self,
        query: str,
        role: str,
        lang: str,
        answer: str,
        citations: list[dict] | None,
        model: str,
    ) -> None:
        import time

        r = await self._get_redis()
        key = make_key(query, role, lang)
        data = json.dumps(
            {
                "answer": answer,
                "citations": citations or [],
                "model": model,
                "cached_at": int(time.time()),
            },
            default=str,
        )
        await r.setex(key, settings.CACHE_L1_TTL_SECONDS, data)
        logger.info("cache_set", key=key[-16:])

    async def invalidate_role(self, role: str) -> int:
        """Drop all cached entries for a role. Use after big doc updates."""
        r = await self._get_redis()
        deleted = 0
        async for key in r.scan_iter(match="cache:l1:*"):
            # We can't decode the role from the hash; this is a coarse invalidation.
            # For per-role precision, prefix with role in the key namespace.
            await r.delete(key)
            deleted += 1
        return deleted

    async def stats(self) -> dict:
        r = await self._get_redis()
        count = 0
        async for _ in r.scan_iter(match="cache:l1:*"):
            count += 1
        return {"entries": count}


l1_cache = L1Cache()
