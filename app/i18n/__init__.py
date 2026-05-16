"""i18n module — language detection + strings + formatters."""
from app.i18n.formatters import fmt_currency, fmt_date, fmt_datetime, fmt_number, fmt_time
from app.i18n.lang_detect import detect_language, normalize_lang
from app.i18n.strings import t

__all__ = [
    "detect_language",
    "normalize_lang",
    "t",
    "fmt_number",
    "fmt_currency",
    "fmt_date",
    "fmt_datetime",
    "fmt_time",
]
