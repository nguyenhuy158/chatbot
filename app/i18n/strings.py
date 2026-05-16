"""i18n string catalog — VN/EN translations for bot-emitted strings.

Keep this small: only strings the bot OWNS (system messages, refusals, welcomes).
LLM-generated text follows user lang naturally; we don't translate it.

Usage:
    from app.i18n.strings import t
    msg = t("quota_exceeded", lang="vi", hours=4)
"""
from string import Formatter


STRINGS: dict[str, dict[str, str]] = {
    # Welcome / onboarding
    "welcome": {
        "vi": "Chào bạn! Tôi là AI chatbot. Tôi có thể giúp bạn tra cứu thông tin, tìm tài liệu, và tự động hóa một số tác vụ.",
        "en": "Hi! I'm the AI chatbot. I can help look up information, find docs, and automate some tasks.",
    },
    "welcome_with_name": {
        "vi": "Chào {name}! Tôi là AI chatbot. Tôi có thể giúp gì cho bạn hôm nay?",
        "en": "Hi {name}! I'm the AI chatbot. How can I help you today?",
    },
    "ai_disclosure": {
        "vi": "Bạn đang chat với AI, không phải người thật. Trả lời có thể sai — vui lòng xác minh thông tin quan trọng.",
        "en": "You are chatting with an AI, not a human. Responses may be inaccurate — please verify important info.",
    },
    "answer_disclaimer": {
        "vi": "AI có thể sai. Vui lòng xác minh thông tin quan trọng.",
        "en": "AI can make mistakes. Please verify important info.",
    },
    # Refusal messages
    "refusal_generic": {
        "vi": "Xin lỗi, tôi không thể trả lời câu hỏi này. Vui lòng đặt câu hỏi khác.",
        "en": "Sorry, I can't help with that. Please ask something else.",
    },
    "refusal_jailbreak": {
        "vi": "Tin nhắn có dấu hiệu cố gắng vượt giới hạn an toàn. Vui lòng đặt câu hỏi bình thường.",
        "en": "Your message appears to attempt to bypass safety guidelines. Please ask a normal question.",
    },
    "refusal_nsfw": {
        "vi": "Nội dung 18+ không được hỗ trợ.",
        "en": "Adult content is not supported.",
    },
    "refusal_acl": {
        "vi": "Bạn không có quyền truy cập nội dung này.",
        "en": "You don't have permission to access this content.",
    },
    # Quota
    "quota_exceeded": {
        "vi": "Bạn đã hết quota hôm nay. Reset sau {hours} giờ.",
        "en": "You've exceeded today's quota. Resets in {hours}h.",
    },
    "quota_warning": {
        "vi": "Bạn đã dùng 80% quota hôm nay ({metric}: {used}/{limit}).",
        "en": "You've used 80% of today's quota ({metric}: {used}/{limit}).",
    },
    # Errors
    "error_generic": {
        "vi": "Xin lỗi, có lỗi xảy ra. Vui lòng thử lại sau.",
        "en": "Sorry, an error occurred. Please try again later.",
    },
    "error_no_kb_match": {
        "vi": "Tôi không tìm thấy thông tin liên quan trong tài liệu. Đây là kiến thức chung của tôi:",
        "en": "I couldn't find this in the knowledge base. Here's my general understanding:",
    },
    # Sources
    "sources_label": {
        "vi": "Nguồn",
        "en": "Sources",
    },
    "page_label": {
        "vi": "trang",
        "en": "page",
    },
    # Onboarding sample prompts (returned by /api/me/onboarding)
    "sample_faq": {
        "vi": "Chính sách hoàn tiền là gì?",
        "en": "What is your refund policy?",
    },
    "sample_doc": {
        "vi": "Cho tôi xem tài liệu hướng dẫn sử dụng",
        "en": "Show me the user guide",
    },
    "sample_calc": {
        "vi": "Tính (1234 + 5678) × 2",
        "en": "Compute (1234 + 5678) × 2",
    },
    "sample_news": {
        "vi": "Tin tức AI tuần này có gì?",
        "en": "What's the latest AI news this week?",
    },
}


def t(key: str, lang: str = "vi", **kwargs) -> str:
    """Translate. Falls back to VN if EN not present, falls back to key if neither."""
    entry = STRINGS.get(key)
    if not entry:
        return key  # unknown key — return as-is to surface bug

    template = entry.get(lang) or entry.get("vi") or entry.get("en") or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def all_keys() -> list[str]:
    return list(STRINGS.keys())
