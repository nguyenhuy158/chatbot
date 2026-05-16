"""Image upload endpoint + describe-on-demand endpoint."""
from uuid import UUID

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel

from app.core.deps import User
from app.core.exceptions import QuotaExceededError
from app.core.logging import get_logger
from app.multimodal import describe_image, save_image
from app.services.quota import quota_service

router = APIRouter()
logger = get_logger(__name__)


class ImageUploadResponse(BaseModel):
    image_id: UUID
    size_bytes: int
    mime: str


class DescribeImageRequest(BaseModel):
    image_id: UUID
    prompt: str = ""
    lang: str = "vi"


class DescribeImageResponse(BaseModel):
    image_id: UUID
    description: str


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_image(
    user: User,
    file: UploadFile = File(...),
) -> ImageUploadResponse:
    content = await file.read()
    if not content:
        raise ValueError("Empty file")

    stored = save_image(
        content=content,
        mime=file.content_type or "application/octet-stream",
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )
    logger.info("image_uploaded", image_id=str(stored.image_id), bytes=stored.size_bytes)
    return ImageUploadResponse(
        image_id=stored.image_id,
        size_bytes=stored.size_bytes,
        mime=stored.mime,
    )


@router.post("/describe", response_model=DescribeImageResponse)
async def describe(req: DescribeImageRequest, user: User) -> DescribeImageResponse:
    """Standalone describe — useful for one-shot image queries.

    The agent (chat endpoint) will also pick up images via state.metadata.image_ids
    in Phase 9.5; for MVP we expose a direct endpoint.
    """
    # Charge a tool_call for vision API usage
    try:
        await quota_service.check_and_reserve(
            user_id=user.user_id, role=user.role, metric="tool_calls", amount=1
        )
    except QuotaExceededError:
        raise

    text = await describe_image(req.image_id, req.prompt, lang=req.lang)
    return DescribeImageResponse(image_id=req.image_id, description=text)
