"""Locale-aware number / date / currency formatting via babel."""
from datetime import datetime
from decimal import Decimal

from babel.dates import format_date, format_datetime, format_time
from babel.numbers import format_currency, format_decimal


LOCALE_MAP = {"vi": "vi_VN", "en": "en_US"}


def _locale(lang: str) -> str:
    return LOCALE_MAP.get(lang, "vi_VN")


def fmt_number(n: int | float | Decimal, lang: str = "vi") -> str:
    """1234567.89 → '1.234.567,89' (vi) or '1,234,567.89' (en)."""
    return format_decimal(n, locale=_locale(lang))


def fmt_currency(amount: int | float | Decimal, lang: str = "vi", currency: str = "VND") -> str:
    """Format with currency symbol per locale."""
    return format_currency(amount, currency, locale=_locale(lang))


def fmt_date(d: datetime, lang: str = "vi") -> str:
    """15/05/2026 (vi) or May 15, 2026 (en)."""
    return format_date(d, locale=_locale(lang), format="short" if lang == "vi" else "long")


def fmt_datetime(d: datetime, lang: str = "vi") -> str:
    return format_datetime(d, locale=_locale(lang), format="short")


def fmt_time(d: datetime, lang: str = "vi") -> str:
    return format_time(d, locale=_locale(lang), format="short")
