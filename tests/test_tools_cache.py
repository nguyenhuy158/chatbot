"""Phase 5 tests — tool registry behavior + cache eligibility."""
from uuid import uuid4

import pytest

from app.services.cache import is_cacheable, make_key
from app.tools import ALL_TOOLS, get_tool_specs_for_llm, get_tools_for_role


# --- Tool registry ---

def test_all_tools_registered() -> None:
    assert "web_search" in ALL_TOOLS
    assert "web_fetch" in ALL_TOOLS
    assert "calculator" in ALL_TOOLS
    assert "get_current_time" in ALL_TOOLS


def test_tool_specs_have_required_keys() -> None:
    specs = get_tool_specs_for_llm("external")
    assert len(specs) > 0
    for spec in specs:
        assert "name" in spec
        assert "description" in spec
        assert "parameters" in spec


def test_tools_for_role_external_includes_basics() -> None:
    tools = get_tools_for_role("external")
    names = {t.name for t in tools}
    # All current tools allow external by default
    assert "web_search" in names
    assert "calculator" in names


# --- Calculator ---

@pytest.mark.asyncio
async def test_calculator_addition() -> None:
    from app.tools.simple import calculator_tool, CalculatorArgs

    result = await calculator_tool.run(
        CalculatorArgs(expression="2 + 3 * 4"),
        user_id=uuid4(),
        tenant_id=uuid4(),
    )
    assert result.success is True
    assert result.output["result"] == 14


@pytest.mark.asyncio
async def test_calculator_blocks_code_injection() -> None:
    from app.tools.simple import calculator_tool, CalculatorArgs

    result = await calculator_tool.run(
        CalculatorArgs(expression="__import__('os').system('ls')"),
        user_id=uuid4(),
        tenant_id=uuid4(),
    )
    assert result.success is False


@pytest.mark.asyncio
async def test_current_time_returns_iso() -> None:
    from app.tools.simple import current_time_tool, CurrentTimeArgs

    result = await current_time_tool.run(
        CurrentTimeArgs(timezone="Asia/Ho_Chi_Minh"),
        user_id=uuid4(),
        tenant_id=uuid4(),
    )
    assert result.success is True
    assert "iso" in result.output
    assert result.output["timezone"] == "Asia/Ho_Chi_Minh"


@pytest.mark.asyncio
async def test_current_time_rejects_bad_tz() -> None:
    from app.tools.simple import current_time_tool, CurrentTimeArgs

    result = await current_time_tool.run(
        CurrentTimeArgs(timezone="NotARealTimezone/Foo"),
        user_id=uuid4(),
        tenant_id=uuid4(),
    )
    assert result.success is False


# --- Cache ---

def test_make_key_normalizes_query() -> None:
    k1 = make_key("Hello WORLD", "external", "vi")
    k2 = make_key("  hello world  ", "external", "vi")
    assert k1 == k2  # case + whitespace normalized


def test_make_key_role_isolated() -> None:
    k1 = make_key("same query", "external", "vi")
    k2 = make_key("same query", "internal", "vi")
    assert k1 != k2  # roles MUST produce different keys


def test_make_key_lang_isolated() -> None:
    k1 = make_key("same", "external", "vi")
    k2 = make_key("same", "external", "en")
    assert k1 != k2


def test_is_cacheable_blocks_personal() -> None:
    assert is_cacheable("Tôi quên password", False, False) is False
    assert is_cacheable("My email is x@y.com", False, False) is False


def test_is_cacheable_blocks_after_tools() -> None:
    # Tool results are usually time-sensitive
    assert is_cacheable("What is Python?", False, True) is False


def test_is_cacheable_blocks_after_memory() -> None:
    # If memory was used, answer is per-user
    assert is_cacheable("What did I say earlier?", True, False) is False


def test_is_cacheable_allows_pure_knowledge() -> None:
    assert is_cacheable("Quy trình duyệt PO là gì?", False, False) is True
    assert is_cacheable("What are the steps for refund?", False, False) is True


def test_is_cacheable_blocks_too_short() -> None:
    assert is_cacheable("hi", False, False) is False
    assert is_cacheable("?", False, False) is False
