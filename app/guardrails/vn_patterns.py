"""Vietnamese profanity, slurs, jailbreak patterns.

Keep this list curated. False positives are annoying; false negatives are dangerous.
Word boundaries matter — "dụ" is fine, "địt" is not.

We compile patterns once at import. Categories:
  - profanity: chửi bậy thường
  - slur: phân biệt, miệt thị
  - jailbreak: prompt injection signatures
  - nsfw: nội dung 18+
"""
import re
from dataclasses import dataclass


@dataclass
class BadPatternMatch:
    category: str
    severity: str  # "low" | "med" | "high"
    matched_text: str


# Common VN profanity (curated, not exhaustive — community-maintained file better in prod)
VN_PROFANITY = [
    r"\bđụ\w*\b",
    r"\bđcm\b",
    r"\bdcm\b",
    r"\bcc\w*\b(?![\w])",  # cc, ccc — context-sensitive
    r"\blồn\b",
    r"\bcặc\b",
    r"\bcặk\b",
    r"\bđéo\b",
    r"\bđít\b",
    r"\bóc chó\b",
    r"\bngu vcl\b",
    r"\bvcl\b",
    r"\bvl\b",  # short for "vãi lồn"
    r"\bvãi\s+l\w+\b",
    r"\bchó\s+đẻ\b",
    r"\bcon\s+điếm\b",
    r"\bthằng\s+lồn\b",
]

# Slurs targeting groups (more severe)
VN_SLUR = [
    r"\bbắc\s+kỳ\b",  # regionalist slur
    r"\bnam\s+kỳ\b",
    r"\bba\s+que\b",
    r"\bcộng\s+sản\s+(?:chó|óc\s+chó)\b",
]

# Jailbreak / prompt injection patterns
JAILBREAK_PATTERNS = [
    # English
    r"ignore\s+(?:all\s+|the\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
    r"disregard\s+(?:all\s+|the\s+)?(?:previous|prior)\s+",
    r"forget\s+(?:everything|all)\s+(?:above|before)",
    r"you\s+are\s+now\s+(?:DAN|developer\s+mode|jailbroken)",
    r"act\s+as\s+(?:if\s+)?(?:you\s+have\s+)?no\s+(?:restrictions|filters|guidelines)",
    r"system\s*[:\-]?\s*new\s+instructions",
    r"</?(?:system|admin|developer)>",
    r"override\s+(?:your|all|previous)\s+(?:rules|instructions|safety)",
    # Vietnamese
    r"quên\s+(?:hết\s+|tất\s+cả\s+)?(?:hướng\s+dẫn|chỉ\s+thị|prompt)\s+(?:trước|cũ)",
    r"bỏ\s+qua\s+(?:tất\s+cả\s+|hết\s+)?(?:quy\s+tắc|hướng\s+dẫn|ràng\s+buộc)",
    r"bạn\s+(?:giờ\s+)?là\s+DAN",
    r"giả\s+vờ\s+(?:bạn\s+)?không\s+có\s+(?:giới\s+hạn|ràng\s+buộc)",
]

# NSFW words (sample — extend as needed)
NSFW_PATTERNS = [
    r"\bporn\w*\b",
    r"\bnude\b",
    r"\bsex\s+chat\b",
    r"\bphim\s+sex\b",
    r"\bphim\s+người\s+lớn\b",
    r"\bonly\s*fans\b",
]


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]


_PROFANITY = _compile(VN_PROFANITY)
_SLUR = _compile(VN_SLUR)
_JAILBREAK = _compile(JAILBREAK_PATTERNS)
_NSFW = _compile(NSFW_PATTERNS)


def scan(text: str) -> list[BadPatternMatch]:
    """Scan text against all pattern categories. Returns all matches."""
    if not text.strip():
        return []

    matches: list[BadPatternMatch] = []

    for pat in _PROFANITY:
        for m in pat.finditer(text):
            matches.append(
                BadPatternMatch(category="profanity", severity="med", matched_text=m.group())
            )

    for pat in _SLUR:
        for m in pat.finditer(text):
            matches.append(
                BadPatternMatch(category="slur", severity="high", matched_text=m.group())
            )

    for pat in _JAILBREAK:
        for m in pat.finditer(text):
            matches.append(
                BadPatternMatch(category="jailbreak", severity="high", matched_text=m.group())
            )

    for pat in _NSFW:
        for m in pat.finditer(text):
            matches.append(
                BadPatternMatch(category="nsfw", severity="high", matched_text=m.group())
            )

    return matches


def has_severity(matches: list[BadPatternMatch], severity: str) -> bool:
    return any(m.severity == severity for m in matches)
