"""Pydantic schemas for chat endpoints."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(..., min_length=1, max_length=10_000)
    stream: bool = True


class Citation(BaseModel):
    source: str
    title: str | None = None
    page: int | None = None
    url: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    content: str
    citations: list[Citation] = []
    model: str
    tokens_input: int
    tokens_output: int
    cost_usd: float
    latency_ms: int
    cached: bool = False
    created_at: datetime


class ConversationSummary(BaseModel):
    id: UUID
    title: str | None
    channel: str
    message_count: int
    last_message_at: datetime
    created_at: datetime
