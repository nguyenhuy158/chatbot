"""Admin endpoints — ban management, quota reset, moderation review.

These are JSON endpoints separate from SQLAdmin (which is read-mostly).
"""
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select, text

from app.core.deps import AdminUser, DbSession
from app.core.exceptions import NotFoundError
from app.db.models import User as UserModel
from app.services.quota import quota_service
from app.services.reputation import admin_unban

router = APIRouter()


class BanRequest(BaseModel):
    user_id: UUID
    hours: int = 24
    reason: str | None = None


class UnbanRequest(BaseModel):
    user_id: UUID
    reset_score: bool = False


class QuotaResetRequest(BaseModel):
    user_id: UUID
    metric: str | None = None  # None = reset all


@router.post("/admin/ban")
async def ban_user(req: BanRequest, admin: AdminUser, db: DbSession) -> dict:
    """Manual ban — sets banned_until and records event."""
    from datetime import datetime, timedelta, timezone

    result = await db.execute(
        select(UserModel).where(
            UserModel.id == req.user_id,
            UserModel.tenant_id == admin.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")

    user.banned_until = datetime.now(timezone.utc) + timedelta(hours=req.hours)
    await db.execute(
        text(
            """
            INSERT INTO moderation_events
                (id, tenant_id, user_id, event_type, severity, content_snippet, action_taken, created_at)
            VALUES
                (gen_random_uuid(), :tenant_id, :user_id, 'manual_ban', 'high', :reason, :action, NOW())
            """
        ),
        {
            "tenant_id": str(admin.tenant_id),
            "user_id": str(req.user_id),
            "reason": req.reason or "manual ban by admin",
            "action": f"banned_{req.hours}h",
        },
    )
    return {"status": "banned", "user_id": str(req.user_id), "until": user.banned_until.isoformat()}


@router.post("/admin/unban")
async def unban_user(req: UnbanRequest, admin: AdminUser, db: DbSession) -> dict:
    user = await admin_unban(db, req.user_id, admin.tenant_id, reset_score=req.reset_score)
    if not user:
        raise NotFoundError("User not found")
    return {"status": "unbanned", "user_id": str(req.user_id), "score": user.reputation_score}


@router.post("/admin/quota/reset")
async def reset_quota(req: QuotaResetRequest, admin: AdminUser) -> dict:
    await quota_service.reset(req.user_id, req.metric)  # type: ignore[arg-type]
    return {"status": "reset", "user_id": str(req.user_id), "metric": req.metric or "all"}


@router.get("/admin/moderation/events")
async def list_moderation_events(
    admin: AdminUser,
    db: DbSession,
    user_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """List recent moderation events for review."""
    sql = """
        SELECT id, user_id, event_type, severity, content_snippet, action_taken, created_at
        FROM moderation_events
        WHERE tenant_id = :tenant_id
    """
    params: dict = {"tenant_id": str(admin.tenant_id), "limit": limit}
    if user_id:
        sql += " AND user_id = :user_id"
        params["user_id"] = str(user_id)
    sql += " ORDER BY created_at DESC LIMIT :limit"

    result = await db.execute(text(sql), params)
    return [dict(r) for r in result.mappings().all()]
