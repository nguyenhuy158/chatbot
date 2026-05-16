"""Phase 4 quota tests (requires Redis — uses fakeredis)."""
import os
from uuid import uuid4

import pytest

# Skip all if fakeredis not installed
fakeredis = pytest.importorskip("fakeredis")


@pytest.fixture
async def quota_with_fake_redis(monkeypatch):
    """Patch quota_service to use fakeredis instead of real Redis."""
    from app.services import quota

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(quota.quota_service, "_redis", fake)
    yield quota.quota_service
    await fake.flushdb()


@pytest.mark.asyncio
async def test_check_and_reserve_increments(quota_with_fake_redis) -> None:
    user_id = uuid4()
    status = await quota_with_fake_redis.check_and_reserve(
        user_id, "external", "messages", amount=1
    )
    assert status.used == 1
    assert status.remaining == 49  # default external limit 50


@pytest.mark.asyncio
async def test_check_and_reserve_blocks_at_limit(quota_with_fake_redis) -> None:
    from app.core.exceptions import QuotaExceededError

    user_id = uuid4()
    # Fill the bucket
    for _ in range(50):
        await quota_with_fake_redis.check_and_reserve(
            user_id, "external", "messages", amount=1
        )

    # Next should raise
    with pytest.raises(QuotaExceededError):
        await quota_with_fake_redis.check_and_reserve(
            user_id, "external", "messages", amount=1
        )


@pytest.mark.asyncio
async def test_internal_quota_higher(quota_with_fake_redis) -> None:
    user_id = uuid4()
    status = await quota_with_fake_redis.check_and_reserve(
        user_id, "internal", "messages", amount=1
    )
    assert status.limit == 500


@pytest.mark.asyncio
async def test_warn_threshold(quota_with_fake_redis) -> None:
    user_id = uuid4()
    # Push to 80%
    for _ in range(40):
        await quota_with_fake_redis.check_and_reserve(
            user_id, "external", "messages", amount=1
        )
    status = await quota_with_fake_redis.get_status(user_id, "external", "messages")
    assert status.warned is True
    assert status.blocked is False


@pytest.mark.asyncio
async def test_reset_clears_counters(quota_with_fake_redis) -> None:
    user_id = uuid4()
    await quota_with_fake_redis.check_and_reserve(user_id, "external", "messages", amount=5)
    await quota_with_fake_redis.reset(user_id, "messages")
    status = await quota_with_fake_redis.get_status(user_id, "external", "messages")
    assert status.used == 0


@pytest.mark.asyncio
async def test_add_increments_without_check(quota_with_fake_redis) -> None:
    user_id = uuid4()
    await quota_with_fake_redis.add(user_id, "external", "tokens", 1000)
    status = await quota_with_fake_redis.get_status(user_id, "external", "tokens")
    assert status.used == 1000
