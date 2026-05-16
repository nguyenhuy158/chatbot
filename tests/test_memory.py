"""Phase 3 unit tests — PII detection + memory extractor parsing."""
import json
import pytest

from app.memory.pii import pii_service


def test_pii_detects_vn_phone() -> None:
    text = "Liên hệ tôi qua số 0912345678 nha"
    detections = pii_service.detect(text)
    types = {d.entity_type for d in detections}
    assert "VN_PHONE" in types or "PHONE_NUMBER" in types


def test_pii_detects_email() -> None:
    text = "Send to huy@techcoop.vn please"
    detections = pii_service.detect(text)
    types = {d.entity_type for d in detections}
    assert "EMAIL_ADDRESS" in types


def test_pii_redact_replaces_email() -> None:
    redacted, detections = pii_service.redact("Mail: huy@techcoop.vn")
    assert "huy@techcoop.vn" not in redacted
    assert "[EMAIL]" in redacted or "[REDACTED]" in redacted
    assert len(detections) >= 1


def test_pii_redact_handles_empty() -> None:
    redacted, detections = pii_service.redact("")
    assert redacted == ""
    assert detections == []


def test_pii_redact_passthrough_when_no_pii() -> None:
    clean = "Tôi muốn hỏi về quy trình duyệt PO"
    redacted, detections = pii_service.redact(clean)
    assert redacted == clean
    assert detections == []


def test_pii_detects_vn_cccd() -> None:
    text = "CCCD của tôi là 012345678901"
    detections = pii_service.detect(text)
    types = {d.entity_type for d in detections}
    assert "VN_CCCD" in types


def test_pii_has_pii_threshold() -> None:
    assert pii_service.has_pii("email me at x@y.com") is True
    assert pii_service.has_pii("hello world") is False


# Extractor tests — parsing of LLM JSON output

def test_extractor_handles_malformed_json(monkeypatch) -> None:
    """If LLM returns garbage, extractor should return empty list, not crash."""
    from app.memory import extractor

    class _FakeResponse:
        def __init__(self, content):
            self.content = content

    async def fake_invoke(messages, tier="cheap"):
        return _FakeResponse("not json at all")

    monkeypatch.setattr(extractor.llm_gateway, "invoke", fake_invoke)

    import asyncio
    result = asyncio.run(extractor.extract_memories("hi", "hello"))
    assert result == []


def test_extractor_filters_invalid_types(monkeypatch) -> None:
    from app.memory import extractor

    class _FakeResponse:
        def __init__(self, content):
            self.content = content

    payload = json.dumps({
        "memories": [
            {"type": "factual", "content": "User lives in Saigon"},
            {"type": "invalid_type", "content": "should be filtered"},
            {"type": "preference", "content": ""},  # empty content
        ]
    })

    async def fake_invoke(messages, tier="cheap"):
        return _FakeResponse(payload)

    monkeypatch.setattr(extractor.llm_gateway, "invoke", fake_invoke)

    import asyncio
    result = asyncio.run(extractor.extract_memories("I'm in Saigon", "Got it"))
    assert len(result) == 1
    assert result[0].memory_type == "factual"
    assert "Saigon" in result[0].content
