"""Channel-agnostic agent runner — shared by Slack, Telegram, web.

Pipeline (mirrors web /api/chat but without SSE):
  1. Identity resolve (email → User row, upsert if new)
  2. Ban check
  3. Quota reserve
  4. Input moderation
  5. L1 cache check
  6. Agent run
  7. Output moderation
  8. Persist messages + accounting
  9. Cache save

Returns plain text answer (or refusal message). Caller formats per channel.
"""
from dataclasses import dataclass
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.core.config import settings
from app.core.exceptions import ForbiddenError, ModerationBlockError, QuotaExceededError
from app.core.logging import get_logger
from app.db.models import Conversation, Message, User
from app.db.session import AsyncSessionLocal
from app.guardrails import moderate_input, moderate_output
from app.services.cache import is_cacheable, l1_cache
from app.services.quota import quota_service
from app.services.reputation import check_banned, penalize, record_moderation_event

logger = get_logger(__name__)


@dataclass
class ChannelMessage:
    """Inbound message from any channel."""
    channel: str  # "slack" | "telegram"
    external_user_id: str  # Slack user ID or Telegram chat ID
    external_email: str | None  # email from SSO/profile if known
    external_name: str | None
    text: str
    thread_key: str | None = None  # Slack thread_ts or Telegram chat_id


@dataclass
class ChannelResponse:
    answer: str
    blocked: bool = False
    block_reason: str | None = None
    conversation_id: UUID | None = None


async def resolve_or_create_user(
    db: AsyncSession,
    channel: str,
    external_id: str,
    email: str | None,
    name: str | None,
) -> User:
    """Find or create a User row.

    Strategy:
      - If email known → look up User by email (unify across channels).
      - Else → look up by (sso_provider=channel, sso_subject=external_id).
      - Else → create new external-role User.

    Role assignment: same logic as web auth (domain check).
    """
    if email:
        result = await db.execute(
            select(User).where(
                User.email == email,
                User.tenant_id == settings.DEFAULT_TENANT_ID,
            )
        )
        user = result.scalar_one_or_none()
        if user:
            # Backfill the channel link for future lookup-by-id paths
            if not user.sso_provider:
                user.sso_provider = channel
                user.sso_subject = external_id
            return user

    # Look up by channel identity
    result = await db.execute(
        select(User).where(
            User.sso_provider == channel,
            User.sso_subject == external_id,
            User.tenant_id == settings.DEFAULT_TENANT_ID,
        )
    )
    user = result.scalar_one_or_none()
    if user:
        if email and not user.email.startswith(external_id):
            user.email = email  # email became known later
        return user

    # Create new — external role by default
    role = "external"
    if email and email.endswith("@techcoop.vn"):
        role = "internal"

    user = User(
        id=uuid4(),
        tenant_id=settings.DEFAULT_TENANT_ID,
        email=email or f"{channel}_{external_id}@noreply.local",
        name=name,
        role=role,
        sso_provider=channel,
        sso_subject=external_id,
    )
    db.add(user)
    await db.flush()
    logger.info("user_created_from_channel", channel=channel, email=user.email, role=role)
    return user


async def resolve_or_create_conversation(
    db: AsyncSession,
    user: User,
    channel: str,
    thread_key: str | None,
) -> Conversation:
    """Map a channel thread to a Conversation.

    For Slack: thread_key = thread_ts (or message_ts if not in thread)
    For Telegram: thread_key = chat_id

    Stored as conversations.title prefix `[thread:<key>]` for lookup until
    we add a dedicated channel_thread column. Phase 7.5 should normalize.
    """
    if thread_key:
        marker = f"[thread:{channel}:{thread_key}]"
        result = await db.execute(
            select(Conversation).where(
                Conversation.user_id == user.id,
                Conversation.tenant_id == user.tenant_id,
                Conversation.channel == channel,
                Conversation.title.startswith(marker),
            )
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(
        id=uuid4(),
        tenant_id=user.tenant_id,
        user_id=user.id,
        title=f"[thread:{channel}:{thread_key}]" if thread_key else f"[{channel}]",
        channel=channel,
    )
    db.add(conv)
    await db.flush()
    return conv


async def handle_channel_message(msg: ChannelMessage) -> ChannelResponse:
    """End-to-end pipeline for any channel. Returns ChannelResponse with answer or block."""
    async with AsyncSessionLocal() as db:
        # 1. Identity
        user = await resolve_or_create_user(
            db=db,
            channel=msg.channel,
            external_id=msg.external_user_id,
            email=msg.external_email,
            name=msg.external_name,
        )

        # 2. Ban
        try:
            await check_banned(db, user.id, user.tenant_id)
        except ForbiddenError as e:
            return ChannelResponse(answer=str(e), blocked=True, block_reason="banned")

        # 3. Quota
        try:
            await quota_service.check_and_reserve(
                user_id=user.id, role=user.role, metric="messages", amount=1
            )
        except QuotaExceededError as e:
            return ChannelResponse(
                answer=f"Bạn đã hết quota hôm nay ({user.role}). Reset sau {e.extra.get('resets_at', 0) // 3600}h.",
                blocked=True,
                block_reason="quota",
            )

        # 4. Input moderation
        decision = await moderate_input(
            text=msg.text, user_role=user.role, user_reputation=user.reputation_score
        )
        if not decision.allow:
            await record_moderation_event(
                db=db,
                tenant_id=user.tenant_id,
                user_id=user.id,
                event_type=decision.reason,
                severity=decision.severity,
                content_snippet=msg.text,
                action_taken="refused",
            )
            await penalize(
                db=db,
                user_id=user.id,
                tenant_id=user.tenant_id,
                severity=decision.severity,
                reason=decision.reason,
            )
            await db.commit()
            return ChannelResponse(
                answer=decision.explanation,
                blocked=True,
                block_reason=decision.reason,
            )

        # Conversation
        conv = await resolve_or_create_conversation(db, user, msg.channel, msg.thread_key)

        # Persist user message
        user_msg = Message(
            tenant_id=user.tenant_id,
            conversation_id=conv.id,
            role="user",
            content=msg.text,
        )
        db.add(user_msg)
        await db.commit()

        # 5. L1 cache check
        cached = await l1_cache.get(msg.text, user.role, "vi")
        if cached:
            assistant_msg = Message(
                tenant_id=user.tenant_id,
                conversation_id=conv.id,
                role="assistant",
                content=cached.answer,
                citations=cached.citations,
                model=cached.model,
                cached=True,
            )
            db.add(assistant_msg)
            await db.commit()
            return ChannelResponse(answer=cached.answer, conversation_id=conv.id)

        # 6. Agent run
        from app.i18n import detect_language
        state: AgentState = {
            "tenant_id": user.tenant_id,
            "user_id": user.id,
            "role": user.role,  # type: ignore[typeddict-item]
            "lang": detect_language(msg.text),
            "messages": [HumanMessage(content=msg.text)],
            "iteration": 0,
            "metadata": {"channel": msg.channel},
        }
        try:
            final = await agent_graph.ainvoke(state)
            answer = final.get("final_answer", "")
            used_memory = bool(final.get("memories"))
            used_tools = bool(final.get("tool_results"))
        except Exception as e:
            logger.exception("agent_failed_channel", channel=msg.channel)
            return ChannelResponse(
                answer="Xin lỗi, có lỗi xảy ra. Vui lòng thử lại.",
                blocked=True,
                block_reason="agent_error",
            )

        # 7. Output moderation
        out_decision = await moderate_output(answer)
        if not out_decision.allow:
            answer = "Xin lỗi, tôi không thể trả lời câu hỏi này. Vui lòng đặt câu hỏi khác."

        # 8. Persist assistant message
        assistant_msg = Message(
            tenant_id=user.tenant_id,
            conversation_id=conv.id,
            role="assistant",
            content=answer,
        )
        db.add(assistant_msg)
        await db.commit()

        # 9. Cache save (if safe)
        if out_decision.allow and is_cacheable(msg.text, used_memory, used_tools):
            try:
                await l1_cache.set(
                    query=msg.text,
                    role=user.role,
                    lang="vi",
                    answer=answer,
                    citations=final.get("rag_citations") or [],
                    model="agent",
                )
            except Exception:
                pass

        return ChannelResponse(answer=answer, conversation_id=conv.id)
