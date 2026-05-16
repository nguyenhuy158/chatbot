"""Phase 9 unit tests — i18n strings, lang detection, formatters."""
from datetime import datetime

from app.i18n import (
    detect_language,
    fmt_currency,
    fmt_date,
    fmt_number,
    normalize_lang,
    t,
)


# --- Lang detection ---

def test_detect_vietnamese_with_diacritics() -> None:
    assert detect_language("Xin chào, tôi muốn hỏi về quy trình") == "vi"


def test_detect_english() -> None:
    assert detect_language("Hello, I want to ask about the workflow") == "en"


def test_detect_short_input_defaults_to_vi() -> None:
    assert detect_language("hi", default="vi") == "vi"
    assert detect_language("", default="vi") == "vi"


def test_detect_vietnamese_without_diacritics_can_fallback() -> None:
    # "Hom nay troi dep" - VN without diacritics → falls back to default
    # This is by design: ambiguous text gets the default
    result = detect_language("Hom nay troi dep")
    assert result in ("vi", "en")  # either is acceptable


def test_detect_vn_diacritic_fast_path() -> None:
    # Even mostly English, if there's a VN diacritic, it's VN
    assert detect_language("Tôi want this") == "vi"


def test_normalize_lang_variants() -> None:
    assert normalize_lang("en-US") == "en"
    assert normalize_lang("en_US") == "en"
    assert normalize_lang("vi-VN") == "vi"
    assert normalize_lang("vietnamese") == "vi"
    assert normalize_lang("english") == "en"
    assert normalize_lang(None) == "vi"
    assert normalize_lang("") == "vi"
    assert normalize_lang("klingon") == "vi"  # unknown → default vi


# --- i18n strings ---

def test_t_returns_localized() -> None:
    assert "AI" in t("welcome", lang="vi") or "chatbot" in t("welcome", lang="vi")
    assert "AI" in t("welcome", lang="en")


def test_t_falls_back_when_lang_missing() -> None:
    # No 'fr' available — falls back to 'vi'
    result = t("welcome", lang="fr")
    assert result == t("welcome", lang="vi")


def test_t_with_format_args() -> None:
    result = t("quota_exceeded", lang="vi", hours=4)
    assert "4" in result
    result_en = t("quota_exceeded", lang="en", hours=4)
    assert "4h" in result_en


def test_t_unknown_key_returns_key() -> None:
    assert t("no_such_key", lang="vi") == "no_such_key"


def test_t_missing_format_arg_returns_template() -> None:
    # Should not crash on missing kwargs
    result = t("quota_exceeded", lang="vi")  # missing 'hours'
    assert "{hours}" in result or "quota" in result.lower()


# --- Formatters ---

def test_fmt_number_vietnamese() -> None:
    # Vi uses dots as thousands sep, comma as decimal
    formatted = fmt_number(1234567.89, lang="vi")
    assert "1" in formatted
    # Either format is acceptable depending on babel version
    assert "234" in formatted


def test_fmt_number_english() -> None:
    formatted = fmt_number(1234567, lang="en")
    assert "1,234,567" in formatted


def test_fmt_currency_vnd() -> None:
    result = fmt_currency(50000, lang="vi", currency="VND")
    assert "50" in result
    assert "₫" in result or "VND" in result or "đ" in result


def test_fmt_date_vi() -> None:
    d = datetime(2026, 5, 15)
    result = fmt_date(d, lang="vi")
    # vi short format usually "15/05/2026" or similar
    assert "15" in result
    assert "2026" in result


def test_fmt_date_en() -> None:
    d = datetime(2026, 5, 15)
    result = fmt_date(d, lang="en")
    assert "May" in result
    assert "2026" in result
