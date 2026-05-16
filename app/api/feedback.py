"""Feedback endpoints — thumbs up/down + admin review queue."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from app.core.deps import AdminUser, DbSession, User
from app.core.exceptions import NotFoundError
from app.db.models import Feedback, Message

router = APIRouter()


class FeedbackRequest(BaseModel):
    message_id: UUID
    rating: int = Field(..., ge=-1, le=1)
    comment: str | None = Field(None, max_length=1000)


class FeedbackOut(BaseModel):
    id: UUID
    message_id: UUID
    user_id: UUID
    rating: int
    comment: str | None
    reviewed_action: str | None
    created_at: str


@router.post("/feedback", response_model=FeedbackOut)
async def submit_feedback(req: FeedbackRequest, user: User, db: DbSession) -> FeedbackOut:
    # Ensure message belongs to user's tenant + their conversation
    result = await db.execute(
        select(Message).where(
            Message.id == req.message_id,
            Message.tenant_id == user.tenant_id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise NotFoundError("Message not found")

    fb = Feedback(
        id=uuid4(),
        tenant_id=user.tenant_id,
        message_id=req.message_id,
        user_id=user.user_id,
        rating=req.rating,
        comment=req.comment,
    )
    db.add(fb)
    await db.flush()
    return FeedbackOut(
        id=fb.id,
        message_id=fb.message_id,
        user_id=fb.user_id,
        rating=fb.rating,
        comment=fb.comment,
        reviewed_action=fb.reviewed_action,
        created_at=fb.created_at.isoformat(),
    )


@router.get("/admin/feedback/queue")
async def feedback_queue(
    admin: AdminUser,
    db: DbSession,
    rating: int | None = Query(None, ge=-1, le=1),
    unreviewed_only: bool = True,
    limit: int = 50,
) -> list[dict]:
    """List feedback for admin review. Defaults to unreviewed thumbs-down."""
    sql = """
        SELECT
            f.id, f.message_id, f.user_id, f.rating, f.comment,
            f.reviewed_action, f.created_at,
            m.content AS message_content
        FROM feedback f
        JOIN messages m ON m.id = f.message_id
        WHERE f.tenant_id = :tenant_id
    """
    params: dict = {"tenant_id": str(admin.tenant_id), "limit": limit}
    if rating is not None:
        sql += " AND f.rating = :rating"
        params["rating"] = rating
    elif unreviewed_only:
        sql += " AND f.rating = -1 AND f.reviewed_action IS NULL"
    sql += " ORDER BY f.created_at DESC LIMIT :limit"

    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]


class FeedbackReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(acknowledged|will_fix|wont_fix|escalate)$")
    note: str | None = Field(None, max_length=500)


@router.patch("/admin/feedback/{feedback_id}")
async def review_feedback(
    feedback_id: UUID,
    req: FeedbackReviewRequest,
    admin: AdminUser,
    db: DbSession,
) -> dict:
    result = await db.execute(
        select(Feedback).where(
            Feedback.id == feedback_id,
            Feedback.tenant_id == admin.tenant_id,
        )
    )
    fb = result.scalar_one_or_none()
    if not fb:
        raise NotFoundError("Feedback not found")

    fb.reviewed_by = admin.user_id
    fb.reviewed_action = req.action
    if req.note:
        fb.comment = (fb.comment or "") + f"\n[Admin {admin.user_id}]: {req.note}"
    return {"status": "reviewed", "action": req.action}


@router.get("/admin/feedback/stats")
async def feedback_stats(admin: AdminUser, db: DbSession) -> dict:
    """Aggregate stats for dashboard."""
    sql = """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE rating = 1) AS thumbs_up,
            COUNT(*) FILTER (WHERE rating = -1) AS thumbs_down,
            COUNT(*) FILTER (WHERE rating = -1 AND reviewed_action IS NULL) AS pending_review,
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS last_7d
        FROM feedback
        WHERE tenant_id = :tenant_id
    """
    result = await db.execute(text(sql), {"tenant_id": str(admin.tenant_id)})
    row = result.mappings().first()
    if not row:
        return {"total": 0, "thumbs_up": 0, "thumbs_down": 0, "pending_review": 0, "csat": None}

    total = row["total"]
    up = row["thumbs_up"]
    down = row["thumbs_down"]
    csat = (up / (up + down)) if (up + down) else None
    return {
        "total": total,
        "thumbs_up": up,
        "thumbs_down": down,
        "pending_review": row["pending_review"],
        "last_7d": row["last_7d"],
        "csat": round(csat, 3) if csat is not None else None,
    }
