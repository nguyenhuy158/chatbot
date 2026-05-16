"""Phase 7 tests — channel-agnostic logic that doesn't need real Slack/Telegram."""
import pytest

from app.channels.telegram import _split_for_telegram


def test_telegram_split_short_passthrough() -> None:
    text = "Hello world"
    result = _split_for_telegram(text)
    assert result == [text]


def test_telegram_split_long_text() -> None:
    text = "A" * 5000
    parts = _split_for_telegram(text, max_len=2000)
    assert len(parts) >= 3
    # No part exceeds limit
    for p in parts:
        assert len(p) <= 2000
    # Recombined matches
    assert "".join(parts).replace("\n", "") == text


def test_telegram_split_prefers_newline_breaks() -> None:
    text = "para1\n" * 100 + "para2\n" * 100 + "para3\n" * 100
    parts = _split_for_telegram(text, max_len=300)
    # Each break should land on a newline boundary if possible
    for p in parts[:-1]:
        # last char before split should not be mid-word
        assert p.endswith("\n") or len(p) == 300


def test_telegram_split_exactly_at_limit() -> None:
    text = "X" * 4000
    parts = _split_for_telegram(text, max_len=4000)
    assert len(parts) == 1


# --- Identity resolver: uses in-memory async session via fixture ---
# Full integration test requires DB; we keep a unit test for the unify-by-email logic.

@pytest.mark.asyncio
async def test_resolve_user_unifies_by_email(monkeypatch) -> None:
    """If a User exists with the same email, channel handler should reuse it
    rather than creating a duplicate."""
    from app.channels import runner
    from app.db.models import User
    from uuid import uuid4

    # Fake DB session that tracks add() calls and supports execute
    class _FakeScalar:
        def __init__(self, value):
            self._value = value
        def scalar_one_or_none(self):
            return self._value

    existing = User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="huy@techcoop.vn",
        name="Huy",
        role="internal",
    )

    added = []

    class FakeDB:
        async def execute(self, stmt, params=None):
            # First call returns existing user (by email); subsequent return None
            if not getattr(self, "_called_once", False):
                self._called_once = True
                return _FakeScalar(existing)
            return _FakeScalar(None)

        def add(self, obj):
            added.append(obj)

        async def flush(self):
            pass

    result = await runner.resolve_or_create_user(
        db=FakeDB(),
        channel="slack",
        external_id="U123",
        email="huy@techcoop.vn",
        name="Huy",
    )
    assert result is existing
    assert added == []  # no new user created
    # Backfilled channel link
    assert existing.sso_provider == "slack"
    assert existing.sso_subject == "U123"
