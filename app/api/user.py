"""User settings + GDPR data access/delete."""
from fastapi import APIRouter
from sqlalchemy import delete, select

from app.core.deps import DbSession, User
from app.db.models import Conversation, User as UserModel
from app.memory import memory_store

router = APIRouter()


@router.get("/settings")
async def get_settings(user: User, db: DbSession):
    result = await db.execute(select(UserModel).where(UserModel.id == user.user_id))
    u = result.scalar_one()
    return {
        "email": u.email,
        "name": u.name,
        "role": u.role,
        "preferences": u.preferences,
    }


@router.put("/settings")
async def update_settings(prefs: dict, user: User, db: DbSession):
    result = await db.execute(select(UserModel).where(UserModel.id == user.user_id))
    u = result.scalar_one()
    u.preferences = {**(u.preferences or {}), **prefs}
    return {"status": "updated"}


@router.get("/data")
async def export_data(user: User, db: DbSession):
    """GDPR right to access. Returns JSON of all user data."""
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.user_id)
    )
    conversations = result.scalars().all()
    return {
        "user_id": str(user.user_id),
        "conversations": [
            {
                "id": str(c.id),
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "messages": [
                    {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                    for m in c.messages
                ],
            }
            for c in conversations
        ],
    }


@router.delete("/data", status_code=204)
async def delete_data(user: User, db: DbSession):
    """GDPR right to be forgotten. Hard delete user data."""
    await db.execute(delete(Conversation).where(Conversation.user_id == user.user_id))
    await memory_store.delete_all_for_user(db, user.tenant_id, user.user_id)
    await db.execute(delete(UserModel).where(UserModel.id == user.user_id))


@router.get("/quota")
async def get_quota(user: User):
    """Show current quota usage across all metrics."""
    from app.services.quota import quota_service

    snapshot = await quota_service.get_all(user.user_id, user.role)
    return {
        metric: {
            "used": status.used,
            "limit": status.limit,
            "remaining": status.remaining,
            "percent": round(status.percent, 1),
            "blocked": status.blocked,
            "warned": status.warned,
        }
        for metric, status in snapshot.items()
    }
