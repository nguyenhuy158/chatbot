"""Telegram bot — webhook-based handler.

Uses python-telegram-bot v21+ async. Mounted on /telegram/webhook of FastAPI.

Setup:
  1. Create bot via @BotFather, get TELEGRAM_BOT_TOKEN
  2. Set webhook URL: curl https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<your-host>/telegram/webhook
  3. Optional: set webhook secret_token for extra verification
"""
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_telegram_app():
    """Build the python-telegram-bot Application. Returns None if not configured."""
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.info("telegram_not_configured")
        return None

    from telegram import Update
    from telegram.ext import (
        Application,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )

    async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Chào bạn! Tôi là AI chatbot. Hỏi tôi bất cứ điều gì về sản phẩm / quy trình. "
            "Gõ /help để xem các lệnh."
        )

    async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "Các lệnh:\n"
            "/start - giới thiệu\n"
            "/help - xem lệnh\n"
            "/link <email> - liên kết tài khoản Telegram với email công ty\n"
            "/reset - bắt đầu cuộc hội thoại mới\n\n"
            "Hoặc cứ nhắn tin bình thường để hỏi."
        )

    async def on_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Link Telegram account to a company email.

        For now we accept the email at face value if it ends with the company
        domain. For production: send a verification code to that email.
        """
        if not context.args:
            await update.message.reply_text("Cú pháp: /link your@email.com")
            return
        email = context.args[0].strip().lower()

        # Validate format
        import re
        if not re.fullmatch(r"[^@]+@[^@]+\.[^@]+", email):
            await update.message.reply_text("Email không hợp lệ.")
            return

        # Persist linkage by updating the User row associated with this Telegram chat
        from sqlalchemy import select
        from app.channels.runner import resolve_or_create_user
        from app.db.session import AsyncSessionLocal
        from app.db.models import User as UserModel

        async with AsyncSessionLocal() as db:
            user = await resolve_or_create_user(
                db=db,
                channel="telegram",
                external_id=str(update.effective_user.id),
                email=None,
                name=update.effective_user.full_name,
            )
            # If another user already owns this email, merge or refuse
            result = await db.execute(
                select(UserModel).where(
                    UserModel.email == email,
                    UserModel.tenant_id == user.tenant_id,
                    UserModel.id != user.id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # Re-link: point the channel identity to the existing email-user
                existing.sso_provider = "telegram"
                existing.sso_subject = str(update.effective_user.id)
                # Soft-delete the just-created user
                await db.delete(user)
                await db.commit()
                await update.message.reply_text(
                    f"Đã liên kết Telegram với tài khoản {email}. Bạn có thể tiếp tục chat bình thường."
                )
                return

            user.email = email
            if email.endswith("@techcoop.vn"):
                user.role = "internal"
            await db.commit()
            await update.message.reply_text(
                f"Đã liên kết email {email} với Telegram của bạn. Role: {user.role}."
            )

    async def on_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Conversation isolation in Telegram is per chat_id. Reset = new conv next msg.
        # For now we just notify; conversation auto-creates fresh thread when not found.
        await update.message.reply_text(
            "Đã reset. Tin nhắn tiếp theo sẽ bắt đầu cuộc hội thoại mới."
        )
        # TODO: mark current conversation closed in DB so resolve_or_create_conversation skips it

    async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        from app.channels.runner import ChannelMessage, handle_channel_message

        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()
        if not text:
            return

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        msg = ChannelMessage(
            channel="telegram",
            external_user_id=str(update.effective_user.id),
            external_email=None,  # set via /link command
            external_name=update.effective_user.full_name,
            text=text,
            thread_key=str(update.effective_chat.id),
        )
        response = await handle_channel_message(msg)
        # Telegram has 4096 char limit per message
        for chunk in _split_for_telegram(response.answer):
            await update.message.reply_text(chunk, parse_mode=None)

    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("help", on_help))
    application.add_handler(CommandHandler("link", on_link))
    application.add_handler(CommandHandler("reset", on_reset))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    return application


def _split_for_telegram(text: str, max_len: int = 4000) -> list[str]:
    """Split text into chunks under Telegram's 4096 char limit. Try to break on newlines."""
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    remaining = text
    while len(remaining) > max_len:
        # Find last newline before limit
        cut = remaining.rfind("\n", 0, max_len)
        if cut == -1:
            cut = max_len
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts


# Singleton application — initialized at startup
_app_singleton = None


async def get_application():
    global _app_singleton
    if _app_singleton is None:
        _app_singleton = build_telegram_app()
        if _app_singleton:
            await _app_singleton.initialize()
    return _app_singleton


async def mount_telegram(fastapi_app) -> None:
    """Register webhook endpoint on FastAPI app."""
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    @fastapi_app.post("/telegram/webhook")
    async def telegram_webhook(req: dict):  # type: ignore[no-untyped-def]
        from telegram import Update

        application = await get_application()
        if not application:
            return {"ok": False, "error": "not configured"}
        update = Update.de_json(req, application.bot)
        await application.process_update(update)
        return {"ok": True}

    logger.info("telegram_mounted")
