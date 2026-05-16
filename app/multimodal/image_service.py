"""Image attachment handling — upload, storage, multimodal LLM call.

MVP scope: upload an image, attach to next chat message, agent uses Gemini Flash
to interpret it. We store images on local disk for now (Phase 9.5: Azure Blob).

Image lifecycle:
  1. POST /api/images/upload → returns {image_id, url}
  2. POST /api/chat with image_id in body → agent loads image, sends multimodal
  3. After 24h: scheduled task cleans up unreferenced images
"""
import asyncio
import base64
import hashlib
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import google.generativeai as genai
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

IMAGES_DIR = Path("/tmp/chatbot-images")
IMAGES_DIR.mkdir(exist_ok=True)

ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass
class StoredImage:
    image_id: UUID
    path: Path
    mime: str
    size_bytes: int
    user_id: UUID
    tenant_id: UUID
    sha256: str


def _path_for(image_id: UUID, ext: str) -> Path:
    return IMAGES_DIR / f"{image_id}{ext}"


def save_image(
    content: bytes,
    mime: str,
    user_id: UUID,
    tenant_id: UUID,
) -> StoredImage:
    """Save raw bytes to disk. Validates mime + size."""
    if mime not in ALLOWED_MIME:
        raise ValueError(f"Unsupported image type: {mime}")
    if len(content) > MAX_BYTES:
        raise ValueError(f"Image too large: {len(content)} > {MAX_BYTES}")

    ext = mimetypes.guess_extension(mime) or ".bin"
    image_id = uuid4()
    path = _path_for(image_id, ext)
    path.write_bytes(content)

    sha256 = hashlib.sha256(content).hexdigest()
    return StoredImage(
        image_id=image_id,
        path=path,
        mime=mime,
        size_bytes=len(content),
        user_id=user_id,
        tenant_id=tenant_id,
        sha256=sha256,
    )


def load_image_bytes(image_id: UUID) -> tuple[bytes, str] | None:
    """Find image on disk by id. Returns (bytes, mime) or None."""
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = _path_for(image_id, ext)
        if path.exists():
            mime, _ = mimetypes.guess_type(str(path))
            return path.read_bytes(), (mime or "application/octet-stream")
    return None


async def describe_image(
    image_id: UUID,
    user_prompt: str,
    lang: str = "vi",
) -> str:
    """Call Gemini Flash multimodal. Returns text answer or raises."""
    if not settings.GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY not configured")

    img_data = load_image_bytes(image_id)
    if img_data is None:
        raise FileNotFoundError(f"Image {image_id} not found")
    image_bytes, mime = img_data

    # google-generativeai is sync — run in executor
    def _sync_call() -> str:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(settings.LLM_CHEAP_MODEL)
        system_hint = (
            "Bạn là trợ lý phân tích hình ảnh. Trả lời ngắn gọn bằng tiếng Việt."
            if lang == "vi"
            else "You are an image analysis assistant. Respond concisely in English."
        )
        prompt = f"{system_hint}\n\nUser question: {user_prompt or 'Describe what you see.'}"
        response = model.generate_content(
            [
                {"mime_type": mime, "data": image_bytes},
                prompt,
            ]
        )
        return response.text or ""

    loop = asyncio.get_event_loop()
    started = time.perf_counter()
    text = await loop.run_in_executor(None, _sync_call)
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info("image_described", image_id=str(image_id), duration_ms=duration_ms, lang=lang)
    return text


def cleanup_stale(older_than_hours: int = 24) -> int:
    """Delete images on disk older than N hours. Returns count deleted."""
    cutoff = time.time() - older_than_hours * 3600
    deleted = 0
    for path in IMAGES_DIR.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
                deleted += 1
            except OSError:
                pass
    return deleted
