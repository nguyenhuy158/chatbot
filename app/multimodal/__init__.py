"""Multimodal module — image upload + Gemini Flash vision."""
from app.multimodal.image_service import (
    StoredImage,
    cleanup_stale,
    describe_image,
    load_image_bytes,
    save_image,
)

__all__ = [
    "StoredImage",
    "cleanup_stale",
    "describe_image",
    "load_image_bytes",
    "save_image",
]
