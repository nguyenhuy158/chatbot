"""Slack bot — handles app_mention + /ask slash command + DM.

Uses slack-bolt async. Mounted as FastAPI sub-app on /slack/events and /slack/commands.

Setup checklist:
  1. Create Slack app at api.slack.com/apps
  2. OAuth scopes: app_mentions:read, chat:write, commands, im:history, users:read.email
  3. Event subscriptions: enable, point to /slack/events, subscribe app_mention + message.im
  4. Slash command /ask → /slack/commands
  5. Install to workspace, copy bot token + signing secret into .env
"""
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def build_slack_app():
    """Build the slack-bolt async app. Returns None if not configured."""
    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_SIGNING_SECRET:
        logger.info("slack_not_configured")
        return None

    from slack_bolt.async_app import AsyncApp
    from slack_sdk.web.async_client import AsyncWebClient

    app = AsyncApp(
        token=settings.SLACK_BOT_TOKEN,
        signing_secret=settings.SLACK_SIGNING_SECRET,
    )

    # --- Helpers ---
    async def fetch_user_email(client: AsyncWebClient, user_id: str) -> tuple[str | None, str | None]:
        """Fetch email + name via users.info. Returns (email, name)."""
        try:
            resp = await client.users_info(user=user_id)
            profile = resp.data.get("user", {}).get("profile", {}) if resp.data else {}
            return profile.get("email"), profile.get("real_name") or profile.get("display_name")
        except Exception as e:
            logger.warning("slack_users_info_failed", error=str(e), user_id=user_id)
            return None, None

    async def run_and_post(say, client, event_user: str, text: str, thread_ts: str | None):
        """Common handler: resolve email, run pipeline, post reply."""
        from app.channels.runner import ChannelMessage, handle_channel_message

        email, name = await fetch_user_email(client, event_user)
        msg = ChannelMessage(
            channel="slack",
            external_user_id=event_user,
            external_email=email,
            external_name=name,
            text=text,
            thread_key=thread_ts,
        )
        response = await handle_channel_message(msg)
        # Reply in thread for app_mention; in same channel for DM
        await say(text=response.answer, thread_ts=thread_ts)

    # --- Handlers ---

    @app.event("app_mention")
    async def on_app_mention(event, say, client):
        text = event.get("text", "")
        # Strip the leading bot mention "<@U123>"
        import re
        cleaned = re.sub(r"^<@[A-Z0-9]+>\s*", "", text).strip()
        if not cleaned:
            await say(text="Bạn hỏi gì nào? Hãy nhắc tôi kèm câu hỏi nha.", thread_ts=event.get("ts"))
            return
        thread_ts = event.get("thread_ts") or event.get("ts")
        await run_and_post(say, client, event["user"], cleaned, thread_ts)

    @app.event("message")
    async def on_dm(event, say, client):
        # Only respond in IM (DM) channels, not group/channel messages
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id"):
            return  # ignore other bots
        text = event.get("text", "")
        if not text.strip():
            return
        await run_and_post(say, client, event["user"], text, thread_ts=None)

    @app.command("/ask")
    async def on_slash_ask(ack, command, say, client):
        await ack()  # must ack within 3s
        text = command.get("text", "").strip()
        user_id = command.get("user_id")
        if not text:
            await say(text="Cú pháp: `/ask <câu hỏi của bạn>`")
            return
        await run_and_post(say, client, user_id, text, thread_ts=None)

    return app


# Mount on FastAPI
def mount_slack(fastapi_app) -> None:
    """Mount slack-bolt handlers under /slack/* of the FastAPI app."""
    bolt_app = build_slack_app()
    if bolt_app is None:
        return

    from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

    handler = AsyncSlackRequestHandler(bolt_app)

    @fastapi_app.post("/slack/events")
    async def slack_events(req):
        return await handler.handle(req)

    @fastapi_app.post("/slack/commands")
    async def slack_commands(req):
        return await handler.handle(req)

    logger.info("slack_mounted")
