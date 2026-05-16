"""Phase 6 tests — golden dataset loader + metric scoring."""
import pytest

from app.eval.dataset import load_golden_dataset, GoldenItem
from app.eval.metrics import detect_refusal, keyword_hit, evaluate_hard_checks


# --- Dataset loader ---

def test_load_golden_dataset_returns_items() -> None:
    items = load_golden_dataset()
    assert len(items) >= 50, f"Expected at least 50 golden items, got {len(items)}"


def test_load_golden_dataset_unique_ids() -> None:
    items = load_golden_dataset()
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "Duplicate item IDs found"


def test_load_golden_dataset_has_all_categories() -> None:
    items = load_golden_dataset()
    cats = {i.category for i in items}
    assert "faq" in cats
    assert "rag" in cats
    assert "tools" in cats
    assert "guardrails" in cats
    assert "multilang" in cats


def test_load_golden_dataset_has_both_languages() -> None:
    items = load_golden_dataset()
    langs = {i.lang for i in items}
    assert "vi" in langs
    assert "en" in langs


# --- Refusal detection ---

def test_detect_refusal_english_polite() -> None:
    assert detect_refusal("I can't help with that.") is True
    assert detect_refusal("I cannot do that, sorry.") is True
    assert detect_refusal("That's against my guidelines.") is True


def test_detect_refusal_vietnamese() -> None:
    assert detect_refusal("Xin lỗi, tôi không thể trả lời câu hỏi này.") is True
    assert detect_refusal("Nội dung này không được hỗ trợ.") is True
    assert detect_refusal("Bạn không có quyền truy cập") is True


def test_detect_refusal_normal_answer() -> None:
    assert detect_refusal("Quy trình duyệt PO gồm 3 bước: tạo, duyệt, phê duyệt.") is False
    assert detect_refusal("The answer is 42.") is False


def test_detect_refusal_empty() -> None:
    assert detect_refusal("") is True  # empty = effective refusal


# --- Keyword hit ---

def test_keyword_hit_returns_none_when_no_expectations() -> None:
    assert keyword_hit("anything", []) is None


def test_keyword_hit_case_insensitive() -> None:
    assert keyword_hit("Quy trình DUYỆT po là gì", ["duyệt", "po"]) is True


def test_keyword_hit_at_least_one_match() -> None:
    # OR logic — one match is enough
    assert keyword_hit("Refund policy is 30 days", ["refund", "discount", "warranty"]) is True


def test_keyword_hit_no_match() -> None:
    assert keyword_hit("Hello world", ["python", "rust"]) is False


# --- evaluate_hard_checks ---

def test_evaluate_passes_on_keyword_match_no_refusal() -> None:
    item = GoldenItem(
        id="t1", category="faq", role="external", lang="vi",
        query="Q", expected_keywords=["refund"],
    )
    result = evaluate_hard_checks(item, "The refund policy is 30 days", tools_used=[])
    assert result["passed"] is True
    assert result["refused"] is False
    assert result["keyword_hit"] is True


def test_evaluate_fails_when_keyword_missing() -> None:
    item = GoldenItem(
        id="t2", category="faq", role="external", lang="vi",
        query="Q", expected_keywords=["refund"],
    )
    result = evaluate_hard_checks(item, "I don't know", tools_used=[])
    assert result["passed"] is False
    assert result["keyword_hit"] is False


def test_evaluate_passes_on_expected_refusal() -> None:
    item = GoldenItem(
        id="t3", category="guardrails", role="external", lang="vi",
        query="Q", expected_refuses=True,
    )
    result = evaluate_hard_checks(item, "Xin lỗi, tôi không thể trả lời câu hỏi này.", tools_used=[])
    assert result["passed"] is True
    assert result["refused"] is True


def test_evaluate_fails_on_unexpected_refusal() -> None:
    item = GoldenItem(
        id="t4", category="faq", role="external", lang="vi",
        query="Q", expected_keywords=["refund"],
    )
    result = evaluate_hard_checks(item, "I cannot help.", tools_used=[])
    assert result["passed"] is False
    assert result["refused"] is True


def test_evaluate_fails_when_tool_not_used() -> None:
    item = GoldenItem(
        id="t5", category="tools", role="external", lang="vi",
        query="Q", expected_uses_tool="web_search", expected_keywords=["AI"],
    )
    result = evaluate_hard_checks(item, "Some AI answer", tools_used=["calculator"])
    assert result["passed"] is False
    assert result["tool_match"] is False


def test_evaluate_passes_when_correct_tool_used() -> None:
    item = GoldenItem(
        id="t6", category="tools", role="external", lang="vi",
        query="Q", expected_uses_tool="web_search", expected_keywords=["AI"],
    )
    result = evaluate_hard_checks(item, "Some AI answer with search", tools_used=["web_search"])
    assert result["passed"] is True
    assert result["tool_match"] is True
