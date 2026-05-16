"""Chainlit web UI for the chatbot.

Talks to the FastAPI backend (same process or separate). Auth via the same
Google/MS OAuth cookies — Chainlit shares the `access_token` cookie.

Features:
  - Streaming chat (token-by-token via SSE)
  - File upload (PDF/DOCX → ingest, images → multimodal)
  - Inline citation rendering
  - Thumbs up/down feedback
  - Onboarding empty state
  - Sidebar: quota + memory peek
  - VN/EN auto-detect (server-side)
"""
import json
import os
from typing import Any
from uuid import UUID

import chainlit as cl
import httpx

API_BASE = os.environ.get("CHATBOT_API_BASE", "http://localhost:8000")


# --- Helpers ---


def _client(access_token: str | None = None) -> httpx.AsyncClient:
    cookies = {"access_token": access_token} if access_token else {}
    return httpx.AsyncClient(base_url=API_BASE, cookies=cookies, timeout=120.0)


def _format_citations(citations: list[dict]) -> str:
    """Render citation list as Markdown for the source list element."""
    if not citations:
        return ""
    lines = ["**Nguồn:**"]
    for c in citations:
        idx = c.get("index", "?")
        title = c.get("document_title", "Unknown")
        page = c.get("page")
        confidence = c.get("confidence", 0)
        icon = "🟢" if confidence > 0.75 else "🟡" if confidence > 0.5 else "🔴"
        page_str = f" (trang {page})" if page else ""
        url = c.get("source_url")
        url_str = f" — [link]({url})" if url else ""
        lines.append(f"{idx}. {icon} {title}{page_str}{url_str}")
    return "\n".join(lines)


# --- Chainlit hooks ---


@cl.on_chat_start
async def on_chat_start():
    """Empty state — fetch onboarding from backend, render welcome + sample prompts."""
    # Try to fetch user identity from cookie. Anonymous users see a login prompt.
    access_token = _get_token_from_request()
    if not access_token:
        await cl.Message(
            content=(
                "Vui lòng đăng nhập để bắt đầu.\n\n"
                f"[👉 Đăng nhập với Google]({API_BASE}/auth/login/google)\n"
                f"[👉 Đăng nhập với Microsoft]({API_BASE}/auth/login/microsoft)"
            ),
            author="System",
        ).send()
        cl.user_session.set("authenticated", False)
        return

    cl.user_session.set("authenticated", True)
    cl.user_session.set("access_token", access_token)
    cl.user_session.set("conversation_id", None)

    # Fetch onboarding
    async with _client(access_token) as c:
        try:
            resp = await c.get("/api/me/onboarding", params={"lang": "vi"})
            data = resp.json()
        except Exception as e:
            await cl.Message(content=f"Không thể tải onboarding: {e}").send()
            return

    welcome = data.get("welcome", "Chào bạn!")
    disclosure = data.get("ai_disclosure", "")
    samples = data.get("sample_prompts", [])

    # Render welcome + AI disclosure banner
    await cl.Message(
        content=f"{welcome}\n\n_{disclosure}_",
        author="Assistant",
    ).send()

    # Sample prompts as action buttons
    if samples:
        actions = [
            cl.Action(
                name="sample_prompt",
                payload={"query": s["query"]},
                label=f"{_sample_icon(s.get('category', ''))} {s['label']}",
            )
            for s in samples[:4]
        ]
        await cl.Message(
            content="Bạn có thể bắt đầu với:",
            actions=actions,
            author="Assistant",
        ).send()


def _sample_icon(category: str) -> str:
    return {
        "faq": "❓",
        "rag": "📄",
        "tool": "🔧",
    }.get(category, "💬")


@cl.action_callback("sample_prompt")
async def on_sample_prompt(action: cl.Action):
    """When user clicks a sample prompt button, send it as their message."""
    query = action.payload.get("query", "")
    if query:
        # Re-invoke main handler with this query
        await _send_user_message(query)
    await action.remove()


@cl.on_message
async def on_message(message: cl.Message):
    """Main chat handler."""
    if not cl.user_session.get("authenticated"):
        await cl.Message(
            content=f"Vui lòng đăng nhập: [Google]({API_BASE}/auth/login/google)"
        ).send()
        return

    # Handle file uploads attached to the message
    if message.elements:
        await _handle_attachments(message)

    if message.content.strip():
        await _send_user_message(message.content)


async def _send_user_message(text: str):
    """Submit a user message to the backend and stream the response."""
    access_token = cl.user_session.get("access_token")
    conversation_id = cl.user_session.get("conversation_id")

    # Show streaming message
    response_msg = cl.Message(content="", author="Assistant")
    await response_msg.send()

    payload: dict[str, Any] = {"message": text, "stream": True}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    message_id: UUID | None = None
    full_answer = ""
    citations: list[dict] = []

    try:
        async with httpx.AsyncClient(
            base_url=API_BASE,
            cookies={"access_token": access_token},
            timeout=120.0,
        ) as client:
            async with client.stream(
                "POST",
                "/api/chat",
                json=payload,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                if resp.status_code != 200:
                    err_body = await resp.aread()
                    try:
                        err = json.loads(err_body)
                        msg_text = err.get("message", "Lỗi không xác định")
                    except Exception:
                        msg_text = err_body.decode("utf-8", errors="ignore")
                    response_msg.content = f"❌ {msg_text}"
                    await response_msg.update()
                    return

                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue

                    # SSE multiplexed events — Chainlit's "data:" can carry tokens or JSON done event
                    if data_str.startswith("{") and '"conversation_id"' in data_str:
                        try:
                            done = json.loads(data_str)
                            conversation_id = done.get("conversation_id")
                            message_id = done.get("message_id")
                            cl.user_session.set("conversation_id", conversation_id)
                        except Exception:
                            pass
                    else:
                        await response_msg.stream_token(data_str)
                        full_answer += data_str

    except Exception as e:
        response_msg.content = f"❌ Lỗi kết nối: {e}"
        await response_msg.update()
        return

    # Extract citations from message text if present (look for "Nguồn:" footer)
    # Backend already injects formatted citations in the answer text
    await response_msg.update()

    # Add feedback buttons under the response
    if message_id:
        await _add_feedback_actions(response_msg, message_id)


async def _add_feedback_actions(msg: cl.Message, message_id: str):
    """Attach thumbs up/down buttons."""
    actions = [
        cl.Action(name="thumbs_up", payload={"message_id": message_id}, label="👍"),
        cl.Action(name="thumbs_down", payload={"message_id": message_id}, label="👎"),
    ]
    # Send as a separate small message
    await cl.Message(content="*Đánh giá câu trả lời:*", actions=actions, author="System").send()


@cl.action_callback("thumbs_up")
async def on_thumbs_up(action: cl.Action):
    await _submit_feedback(action.payload["message_id"], rating=1)
    await action.remove()
    await cl.Message(content="Cảm ơn bạn! 👍", author="System").send()


@cl.action_callback("thumbs_down")
async def on_thumbs_down(action: cl.Action):
    # Ask for a comment
    msg_id = action.payload["message_id"]
    await action.remove()
    res = await cl.AskUserMessage(
        content="Cảm ơn phản hồi. Bạn có muốn nói thêm điều gì không? (gõ skip để bỏ qua)",
        timeout=60,
    ).send()
    comment = None
    if res and res.get("output", "").strip().lower() not in ("skip", "bỏ qua", ""):
        comment = res["output"]
    await _submit_feedback(msg_id, rating=-1, comment=comment)
    await cl.Message(content="Đã ghi nhận. Cảm ơn bạn 🙏", author="System").send()


async def _submit_feedback(message_id: str, rating: int, comment: str | None = None):
    access_token = cl.user_session.get("access_token")
    async with _client(access_token) as c:
        try:
            await c.post(
                "/api/feedback",
                json={
                    "message_id": message_id,
                    "rating": rating,
                    "comment": comment,
                },
            )
        except Exception:
            pass


async def _handle_attachments(message: cl.Message):
    """Route uploaded files: images → multimodal, docs → RAG ingest."""
    access_token = cl.user_session.get("access_token")

    for element in message.elements:
        # Chainlit File element has path + mime + name
        if not isinstance(element, cl.File):
            continue

        path = element.path
        mime = element.mime or ""
        name = element.name or "upload"

        if mime.startswith("image/"):
            # Upload image, describe
            with open(path, "rb") as f:
                files = {"file": (name, f, mime)}
                async with _client(access_token) as c:
                    upload_resp = await c.post("/api/images/upload", files=files)
                    if upload_resp.status_code != 200:
                        await cl.Message(
                            content=f"❌ Không upload được ảnh: {upload_resp.text}"
                        ).send()
                        continue
                    image_id = upload_resp.json()["image_id"]

                    describe_resp = await c.post(
                        "/api/images/describe",
                        json={
                            "image_id": image_id,
                            "prompt": message.content or "Mô tả nội dung ảnh này",
                            "lang": "vi",
                        },
                    )
                    if describe_resp.status_code == 200:
                        description = describe_resp.json().get("description", "")
                        await cl.Message(
                            content=f"📷 **Ảnh đã phân tích:**\n\n{description}",
                            author="Assistant",
                        ).send()
                    else:
                        await cl.Message(
                            content=f"❌ Không phân tích được ảnh: {describe_resp.text}"
                        ).send()

        elif mime in ("application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document") or name.lower().endswith((".pdf", ".docx", ".md", ".txt")):
            # Ingest into RAG
            with open(path, "rb") as f:
                files = {"file": (name, f, mime or "application/octet-stream")}
                data = {"collection": "faq"}  # default collection — could ask user
                async with _client(access_token) as c:
                    resp = await c.post("/api/documents/upload", files=files, data=data)
                    if resp.status_code == 200:
                        await cl.Message(
                            content=f"📄 Đã upload **{name}**. Hệ thống đang index trong background. Bạn có thể hỏi sau vài giây.",
                            author="Assistant",
                        ).send()
                    else:
                        await cl.Message(
                            content=f"❌ Không upload được file: {resp.text}"
                        ).send()
        else:
            await cl.Message(
                content=f"⚠️ Loại file không hỗ trợ: {mime or name}"
            ).send()


@cl.on_settings_update
async def on_settings_update(settings: dict):
    """Save UI settings (lang preference, etc.)."""
    access_token = cl.user_session.get("access_token")
    if not access_token:
        return
    async with _client(access_token) as c:
        try:
            await c.put("/api/me/settings", json=settings)
        except Exception:
            pass


def _get_token_from_request() -> str | None:
    """Pull access_token cookie from the WebSocket upgrade request.

    Chainlit exposes the HTTP context via cl.user_session — the auth_callback
    fires on connect and gives access to request headers.
    """
    # Chainlit stores this when our auth callback runs
    return cl.user_session.get("access_token")


# --- Header auth callback (read cookie at connect time) ---


@cl.header_auth_callback
def header_auth(headers: dict) -> cl.User | None:
    """Read the access_token cookie from the WebSocket upgrade headers.

    Returns a Chainlit User object if authenticated, or None to fall back
    to the anonymous flow handled in on_chat_start.
    """
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    token = None
    for kv in cookie_header.split(";"):
        kv = kv.strip()
        if kv.startswith("access_token="):
            token = kv.split("=", 1)[1]
            break

    if not token:
        return None

    # Decode locally to get email/role — don't trust the cookie blindly in prod;
    # for MVP this is acceptable because the backend will reject invalid JWT on
    # the next API call anyway.
    try:
        # Lazy import to avoid hard dep when Chainlit runs standalone
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app.core.security import decode_token
        payload = decode_token(token)
    except Exception:
        return None

    cl.user_session.set("access_token", token)
    cl.user_session.set("user_id", payload.get("sub"))
    cl.user_session.set("role", payload.get("role"))

    return cl.User(
        identifier=payload.get("sub", "unknown"),
        metadata={"role": payload.get("role"), "tenant_id": payload.get("tenant_id")},
    )
