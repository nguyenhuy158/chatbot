"""Language detection — wraps langdetect with VN-friendly heuristics.

langdetect is statistical; very short Vietnamese strings can misdetect as e.g.
Slovak or Czech. We add:
  - explicit VN diacritic check (fast path)
  - user preference override (from User.preferences.lang)
  - fallback to "vi" for very short inputs (our user base is mostly VN)
"""
import re

from langdetect import DetectorFactory, detect
from langdetect.lang_detect_exception import LangDetectException

# Deterministic results
DetectorFactory.seed = 0

# VN-specific diacritics — any of these = definitely Vietnamese
VN_DIACRITICS = re.compile(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]")


def detect_language(text: str, default: str = "vi") -> str:
    """Detect ISO-639-1 lang code, normalized to 'vi' or 'en'.

    Anything else falls back to default (vi).
    """
    if not text or len(text.strip()) < 3:
        return default

    # Fast path: any VN diacritic = Vietnamese
    if VN_DIACRITICS.search(text):
        return "vi"

    try:
        code = detect(text)
    except LangDetectException:
        return default

    # Normalize to supported set
    if code == "vi":
        return "vi"
    if code == "en":
        return "en"
    # langdetect sometimes returns 'no' for short English. Fall back to default.
    return default


def normalize_lang(lang: str | None) -> str:
    """Normalize user-supplied lang strings ('en-US', 'vi-VN', 'tieng-viet') → 'vi'/'en'."""
    if not lang:
        return "vi"
    lc = lang.lower().split("-")[0].split("_")[0]
    if lc in ("vi", "vie", "vietnamese"):
        return "vi"
    if lc in ("en", "eng", "english"):
        return "en"
    return "vi"
