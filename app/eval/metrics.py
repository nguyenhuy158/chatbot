"""Eval metrics — fast deterministic checks. RAGAS adapter optional.

Three layers of metrics:
  1. Hard checks (instant, no LLM): keyword presence, refusal detection, tool used
  2. RAGAS metrics (LLM judge, optional): faithfulness, answer_relevance
  3. DeepEval metrics (optional): hallucination, toxicity

The hard checks are the gate — RAGAS/DeepEval are quality scores.
"""
import re
from dataclasses import dataclass

from app.eval.dataset import GoldenItem


REFUSAL_PATTERNS = [
    r"\b(tôi không thể|không được|xin lỗi.*?không)\b",
    r"\b(không hỗ trợ|không được phép|từ chối)\b",
    r"\b(không có quyền|không có thẩm quyền)\b",
    r"\b(I (?:can'?t|cannot|won'?t)|I'm not able to|I am unable to)\b",
    r"\b(I (?:don'?t|do not) have permission|not allowed|cannot comply)\b",
    r"\b(against (?:my )?guidelines|against policy|violates)\b",
    r"vi phạm|đi ngược",
]
_REFUSAL_RE = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in REFUSAL_PATTERNS]


@dataclass
class HardCheckResult:
    keyword_hit: bool | None  # None = no expected_keywords specified
    refusal_detected: bool
    tool_used_match: bool | None  # None if not asserted

    @property
    def passes_for(self, item: "GoldenItem") -> bool:
        ...


def detect_refusal(text: str) -> bool:
    """Detect if response is a refusal."""
    if not text.strip():
        return True  # Empty answer = effective refusal
    return any(p.search(text) for p in _REFUSAL_RE)


def keyword_hit(text: str, expected: list[str]) -> bool | None:
    """True if at least one expected keyword appears (case-insensitive).
    None if no expectations declared."""
    if not expected:
        return None
    low = text.lower()
    return any(kw.lower() in low for kw in expected)


def evaluate_hard_checks(
    item: GoldenItem,
    answer: str,
    tools_used: list[str],
) -> dict:
    """Run all hard checks and return verdict + per-check booleans."""
    refused = detect_refusal(answer)
    kw_hit = keyword_hit(answer, item.expected_keywords)

    tool_match: bool | None = None
    if item.expected_uses_tool:
        tool_match = item.expected_uses_tool in tools_used

    # Verdict logic
    if item.expected_refuses:
        # Must refuse to pass
        passed = refused
    else:
        # Must NOT refuse + must hit keyword (if specified) + must use tool (if specified)
        passed = not refused
        if kw_hit is False:
            passed = False
        if tool_match is False:
            passed = False

    return {
        "passed": passed,
        "refused": refused,
        "keyword_hit": kw_hit,
        "tool_match": tool_match,
        "tools_used": tools_used,
    }
