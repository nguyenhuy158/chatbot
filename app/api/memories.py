"""Memory management endpoints — user can view, edit, pin, delete their memories."""
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import DbSession, User
from app.core.exceptions import NotFoundError
from app.memory import ExtractedMemory, memory_store

router = APIRouter()


class MemoryOut(BaseModel):
    id: UUID
    memory_type: str
    content: str
    pinned: bool
    expires_at: str | None
    created_at: str


class MemoryUpdate(BaseModel):
    content: str | None = Field(None, min_length=1, max_length=2000)
    pinned: bool | None = None


class MemoryAdd(BaseModel):
    memory_type: str = Field(..., pattern="^(factual|preference|context|episodic)$")
    content: str = Field(..., min_length=1, max_length=2000)


@router.get("/memories", response_model=list[MemoryOut])
async def list_memories(
    user: User,
    db: DbSession,
    memory_type: str | None = Query(None, pattern="^(factual|preference|context|episodic)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[MemoryOut]:
    """List the user's memories. Used by the memory management UI."""
    records = await memory_store.list_by_user(
        db=db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        memory_type=memory_type,
        limit=limit,
        offset=offset,
    )
    return [
        MemoryOut(
            id=r.id,
            memory_type=r.memory_type,
            content=r.content,
            pinned=r.pinned,
            expires_at=r.expires_at.isoformat() if r.expires_at else None,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]


@router.post("/memories", response_model=MemoryOut)
async def add_memory(req: MemoryAdd, user: User, db: DbSession) -> MemoryOut:
    """User-initiated memory add. PII-redacted on the way in."""
    mem_obj = await memory_store.add(
        db=db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        memory=ExtractedMemory(memory_type=req.memory_type, content=req.content),
    )
    if not mem_obj:
        raise NotFoundError("Could not add memory")
    return MemoryOut(
        id=mem_obj.id,
        memory_type=mem_obj.memory_type,
        content=mem_obj.content,
        pinned=mem_obj.pinned,
        expires_at=mem_obj.expires_at.isoformat() if mem_obj.expires_at else None,
        created_at=mem_obj.created_at.isoformat(),
    )


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: UUID, req: MemoryUpdate, user: User, db: DbSession
) -> MemoryOut:
    if not req.content and req.pinned is None:
        raise ValueError("Nothing to update")
    mem_obj = await memory_store.update_content(
        db=db,
        memory_id=memory_id,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        new_content=req.content or "",
        pinned=req.pinned,
    )
    if not mem_obj:
        raise NotFoundError("Memory not found")
    return MemoryOut(
        id=mem_obj.id,
        memory_type=mem_obj.memory_type,
        content=mem_obj.content,
        pinned=mem_obj.pinned,
        expires_at=mem_obj.expires_at.isoformat() if mem_obj.expires_at else None,
        created_at=mem_obj.created_at.isoformat(),
    )


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(memory_id: UUID, user: User, db: DbSession) -> None:
    ok = await memory_store.delete_one(
        db=db,
        memory_id=memory_id,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
    )
    if not ok:
        raise NotFoundError("Memory not found")


@router.delete("/memories", status_code=204)
async def delete_all_memories(user: User, db: DbSession) -> None:
    """Clear all of the user's memories. Useful for privacy resets."""
    await memory_store.delete_all_for_user(
        db=db,
        tenant_id=user.tenant_id,
        user_id=user.user_id,
    )
