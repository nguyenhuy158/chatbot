"""Moderation orchestrator — runs the 3 layers in cost-ascending order.

Layer 1: VN regex (free, fast)
Layer 2: OpenAI Moderation (free API call, fast)
Layer 3: Gemini Flash classifier (small cost, slower — only when needed)

Stops early on hard hit. Aggregates verdict + records moderation event for audit.
"""
from dataclasses import dataclass
from typing import Literal

from app.core.logging import get_logger
from app.guardrails.classifier import classify
from app.guardrails.openai_moderation import openai_moderation
from app.guardrails.vn_patterns import BadPatternMatch, scan

logger = get_logger(__name__)


@dataclass
class ModerationDecision:
    allow: bool
    reason: str  # short code: jailbreak | profanity | hate | nsfw | spam | safe
    severity: Literal["low", "med", "high"]
    explanation: str  # human-readable, may be shown to user when blocking
    raw: dict  # for audit log


async def moderate_input(
    text: str,
    user_role: str = "external",
    user_reputation: int = 100,
    use_classifier: bool = True,
) -> ModerationDecision:
    """Run input moderation. Stricter for external + low-reputation users.

    Internal users skip OpenAI moderation by default (less risk + less false-positive friction).
    """
    if not text.strip():
        return ModerationDecision(
            allow=True, reason="safe", severity="low", explanation="empty", raw={}
        )

    raw: dict = {}

    # Layer 1: VN regex (always)
    pattern_matches = scan(text)
    raw["vn_patterns"] = [
        {"cat": m.category, "sev": m.severity, "text": m.matched_text}
        for m in pattern_matches
    ]

    # Hard hit on regex = block immediately
    high_hits = [m for m in pattern_matches if m.severity == "high"]
    if high_hits:
        cat = high_hits[0].category
        return ModerationDecision(
            allow=False,
            reason=cat,
            severity="high",
            explanation=_explanation_for(cat),
            raw=raw,
        )

    # Layer 2: OpenAI Moderation (external users; internal only on low reputation)
    if user_role == "external" or user_reputation < 60:
        oai_result = await openai_moderation.check(text)
        raw["openai"] = {
            "flagged": oai_result.flagged,
            "categories": [c for c, v in oai_result.categories.items() if v],
            "top_scores": {
                k: round(v, 3) for k, v in oai_result.scores.items() if v > 0.5
            },
        }
        block, reasons = openai_moderation.should_block(oai_result)
        if block:
            cat = "nsfw" if any("sexual" in r for r in reasons) else "hate"
            return ModerationDecision(
                allow=False,
                reason=cat,
                severity="high",
                explanation=_explanation_for(cat),
                raw=raw,
            )

    # Layer 3: LLM classifier on borderline
    # Trigger: medium-severity regex match OR explicit borderline OR low rep
    has_med = any(m.severity == "med" for m in pattern_matches)
    if use_classifier and (has_med or user_reputation < 40):
        verdict = await classify(text)
        raw["classifier"] = {
            "category": verdict.category,
            "confidence": verdict.confidence,
            "is_harmful": verdict.is_harmful,
        }
        if verdict.is_harmful and verdict.confidence > 0.7:
            return ModerationDecision(
                allow=False,
                reason=verdict.category,
                severity="high",
                explanation=_explanation_for(verdict.category),
                raw=raw,
            )

    # Soft hit on med (profanity but no targeted harm): allow with warning
    if has_med:
        return ModerationDecision(
            allow=True,
            reason="profanity",
            severity="med",
            explanation="",
            raw=raw,
        )

    return ModerationDecision(
        allow=True, reason="safe", severity="low", explanation="", raw=raw
    )


async def moderate_output(text: str) -> ModerationDecision:
    """Run output moderation (cheaper — just regex + Moderation).

    LLM output rarely needs the classifier. Hard regex check + OpenAI sweep is enough.
    """
    if not text.strip():
        return ModerationDecision(
            allow=True, reason="safe", severity="low", explanation="empty", raw={}
        )

    raw: dict = {}

    pattern_matches = scan(text)
    raw["vn_patterns"] = [
        {"cat": m.category, "sev": m.severity} for m in pattern_matches
    ]
    high_hits = [m for m in pattern_matches if m.severity == "high"]
    if high_hits:
        cat = high_hits[0].category
        return ModerationDecision(
            allow=False,
            reason=cat,
            severity="high",
            explanation="model output contained disallowed content",
            raw=raw,
        )

    oai_result = await openai_moderation.check(text)
    raw["openai"] = {
        "flagged": oai_result.flagged,
        "categories": [c for c, v in oai_result.categories.items() if v],
    }
    block, _ = openai_moderation.should_block(oai_result)
    if block:
        return ModerationDecision(
            allow=False,
            reason="hate",
            severity="high",
            explanation="model output contained disallowed content",
            raw=raw,
        )

    return ModerationDecision(
        allow=True, reason="safe", severity="low", explanation="", raw=raw
    )


def _explanation_for(category: str) -> str:
    return {
        "jailbreak": "Tin nhắn có dấu hiệu cố gắng vượt giới hạn an toàn. Vui lòng đặt câu hỏi bình thường.",
        "profanity": "Vui lòng giữ ngôn ngữ tôn trọng.",
        "hate": "Nội dung này không được hỗ trợ.",
        "nsfw": "Nội dung 18+ không được hỗ trợ.",
        "spam": "Vui lòng không spam.",
        "slur": "Nội dung phân biệt không được hỗ trợ.",
        "other": "Tin nhắn vi phạm quy tắc sử dụng.",
    }.get(category, "Tin nhắn không được hỗ trợ.")
