"""Chat endpoint with guardrails + quota pipeline.

Pipeline per request:
  1. check_banned (reject if user banned)
  2. quota check: messages (atomic reserve, raises 429)
  3. moderate_input → block or warn
  4. agent run (RAG + memory + LLM)
  5. moderate_output → block leak/toxic
  6. record tokens + cost to quota (after-the-fact)
  7. stream tokens to client
"""
import json
from uuid import UUID, uuid4

from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.core.deps import DbSession, User
from app.core.exceptions import ModerationBlockError, NotFoundError
from app.core.logging import get_logger
from app.db.models import Conversation, Message
from app.db.session import AsyncSessionLocal
from app.guardrails import moderate_input, moderate_output
from app.schemas.chat import ChatRequest
from app.services.cache import is_cacheable, l1_cache
from app.services.quota import quota_service
from app.services.reputation import (
    check_banned,
    penalize,
    record_moderation_event,
)
from app.i18n import detect_language, normalize_lang

router = APIRouter()
logger = get_logger(__name__)


@router.post("/chat")
async def chat(req: ChatRequest, user: User, db: DbSession):
    """Send a chat message. Returns SSE stream of tokens."""

    # 1. Ban check
    await check_banned(db, user.user_id, user.tenant_id)

    # 2. Quota reserve (messages)
    await quota_service.check_and_reserve(
        user_id=user.user_id, role=user.role, metric="messages", amount=1
    )

    # 3. Get user reputation for moderation tuning
    from app.db.models import User as UserModel
    result = await db.execute(
        select(UserModel.reputation_score).where(UserModel.id == user.user_id)
    )
    reputation = result.scalar_one_or_none() or 100

    # 4. Input moderation
    decision = await moderate_input(
        text=req.message,
        user_role=user.role,
        user_reputation=reputation,
    )
    if not decision.allow:
        # Record event + penalize + maybe ban
        await record_moderation_event(
            db=db,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            event_type=decision.reason,
            severity=decision.severity,
            content_snippet=req.message,
            action_taken="refused",
        )
        await penalize(
            db=db,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            severity=decision.severity,
            reason=decision.reason,
        )
        await db.commit()
        raise ModerationBlockError(decision.explanation, category=decision.reason)

    # Get/create conversation
    if req.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == req.conversation_id,
                Conversation.user_id == user.user_id,
                Conversation.tenant_id == user.tenant_id,
            )
        )
        conv = result.scalar_one_or_none()
        if not conv:
            raise NotFoundError("Conversation not found")
    else:
        conv = Conversation(
            id=uuid4(),
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            title=req.message[:60],
            channel="web",
        )
        db.add(conv)
        await db.flush()

    # Persist user message (use redacted version if soft-moderated?)
    user_msg = Message(
        tenant_id=user.tenant_id,
        conversation_id=conv.id,
        role="user",
        content=req.message,
    )
    db.add(user_msg)
    await db.flush()
    await db.commit()

    initial_state: AgentState = {
        "tenant_id": user.tenant_id,
        "user_id": user.user_id,
        "role": user.role,  # type: ignore[typeddict-item]
        "lang": _detect_lang_for_user(req.message, user_pref=None),
        "messages": [HumanMessage(content=req.message)],
        "iteration": 0,
        "metadata": {},
    }

    async def event_stream():
        try:
            # 4.5. L1 cache check (before agent run)
            cached = await l1_cache.get(req.message, user.role, "vi")
            if cached:
                logger.info("cache_hit", user_id=str(user.user_id))
                # Save cached response as a new message
                async with AsyncSessionLocal() as save_db:
                    assistant_msg = Message(
                        tenant_id=user.tenant_id,
                        conversation_id=conv.id,
                        role="assistant",
                        content=cached.answer,
                        citations=cached.citations,
                        model=cached.model,
                        cached=True,
                    )
                    save_db.add(assistant_msg)
                    await save_db.commit()
                    await save_db.refresh(assistant_msg)
                    assistant_msg_id = assistant_msg.id

                for chunk in chunks(cached.answer, 30):
                    yield {"event": "token", "data": chunk}
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "conversation_id": str(conv.id),
                        "message_id": str(assistant_msg_id),
                        "cached": True,
                    }),
                }
                return

            # Run agent
            final_state = await agent_graph.ainvoke(initial_state)
            answer = final_state.get("final_answer", "")
            used_memory = bool(final_state.get("memories"))
            used_tools = bool(final_state.get("tool_results"))

            # 5. Output moderation
            out_decision = await moderate_output(answer)
            if not out_decision.allow:
                logger.warning(
                    "output_blocked",
                    user_id=str(user.user_id),
                    reason=out_decision.reason,
                )
                async with AsyncSessionLocal() as audit_db:
                    await record_moderation_event(
                        db=audit_db,
                        tenant_id=user.tenant_id,
                        user_id=user.user_id,
                        event_type=f"output_{out_decision.reason}",
                        severity=out_decision.severity,
                        content_snippet=answer,
                        action_taken="replaced",
                    )
                    await audit_db.commit()
                answer = (
                    "Xin lỗi, tôi không thể trả lời câu hỏi này. "
                    "Vui lòng đặt câu hỏi khác."
                )

            # Persist assistant message + token/cost accounting
            tokens_in = final_state.get("metadata", {}).get("tokens_in", 0) or 0
            tokens_out = final_state.get("metadata", {}).get("tokens_out", 0) or 0
            cost_cents = final_state.get("metadata", {}).get("cost_cents", 0) or 0

            async with AsyncSessionLocal() as save_db:
                assistant_msg = Message(
                    tenant_id=user.tenant_id,
                    conversation_id=conv.id,
                    role="assistant",
                    content=answer,
                    tokens_input=tokens_in,
                    tokens_output=tokens_out,
                    cost_usd=cost_cents / 100 if cost_cents else None,
                )
                save_db.add(assistant_msg)
                await save_db.commit()
                await save_db.refresh(assistant_msg)
                assistant_msg_id = assistant_msg.id

            # 6. Update quota counters (no-fail; over-quota for next request)
            if tokens_in + tokens_out > 0:
                await quota_service.add(
                    user.user_id, user.role, "tokens", tokens_in + tokens_out
                )
            if cost_cents > 0:
                await quota_service.add(user.user_id, user.role, "cost_cents", cost_cents)

            # 6.5. L1 cache save (only if safe to cache)
            if out_decision.allow and is_cacheable(req.message, used_memory, used_tools):
                try:
                    await l1_cache.set(
                        query=req.message,
                        role=user.role,
                        lang="vi",
                        answer=answer,
                        citations=final_state.get("rag_citations") or [],
                        model="agent",
                    )
                except Exception as e:
                    logger.warning("cache_save_failed", error=str(e))

            # 7. Stream chunks
            for chunk in chunks(answer, 30):
                yield {"event": "token", "data": chunk}

            yield {
                "event": "done",
                "data": json.dumps({
                    "conversation_id": str(conv.id),
                    "message_id": str(assistant_msg_id),
                    "moderation": {
                        "input_severity": decision.severity,
                        "output_severity": out_decision.severity,
                    },
                }),
            }
        except Exception as e:
            logger.exception("chat_failed", error=str(e))
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_stream())


@router.get("/conversations")
async def list_conversations(user: User, db: DbSession):
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.user_id == user.user_id,
            Conversation.tenant_id == user.tenant_id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(50)
    )
    convs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "channel": c.channel,
            "updated_at": c.updated_at.isoformat(),
        }
        for c in convs
    ]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, user: User, db: DbSession):
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.user_id,
            Conversation.tenant_id == user.tenant_id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise NotFoundError("Conversation not found")
    await db.delete(conv)


def chunks(text: str, size: int):
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _detect_lang_for_user(text: str, user_pref: str | None) -> str:
    """User preference wins; else auto-detect."""
    if user_pref:
        return normalize_lang(user_pref)
    return detect_language(text)
