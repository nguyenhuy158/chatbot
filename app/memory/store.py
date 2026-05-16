"""Memory store — CRUD over pgvector with TTL and similarity dedupe.

Public ops:
  - add(): embed + dedupe + insert
  - search(): semantic search by query
  - list_by_user(): pagination for UI
  - update(): edit content
  - delete(): by id or all for user (GDPR)
  - cleanup_expired(): scheduled task
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Memory
from app.memory.extractor import ExtractedMemory
from app.memory.pii import pii_service
from app.rag.embedder import embedder

logger = get_logger(__name__)


# TTL by memory type
TTL_DAYS: dict[str, int | None] = {
    "factual": None,  # forever
    "preference": None,  # forever
    "context": 30,
    "episodic": 90,
}

# Dedupe threshold: if existing memory is within this cosine distance, update instead of insert
DEDUPE_THRESHOLD = 0.15  # ~0.85 cosine similarity


@dataclass
class MemoryRecord:
    id: UUID
    memory_type: str
    content: str
    pinned: bool
    expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, m: Memory) -> "MemoryRecord":
        return cls(
            id=m.id,
            memory_type=m.memory_type,
            content=m.content,
            pinned=m.pinned,
            expires_at=m.expires_at,
            created_at=m.created_at,
        )


class MemoryStore:
    async def add(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        memory: ExtractedMemory,
        source_message_id: UUID | None = None,
        skip_pii: bool = False,
    ) -> Memory | None:
        """Add a memory. PII-redacts first; dedupes via similarity."""
        # PII guard — drop entirely if too sensitive
        if not skip_pii:
            redacted, detections = pii_service.redact(memory.content)
            if any(d.score > 0.85 for d in detections):
                # High-confidence PII — store redacted version
                content = redacted
                logger.info(
                    "memory_pii_redacted",
                    user_id=str(user_id),
                    entities=[d.entity_type for d in detections],
                )
            else:
                content = memory.content
        else:
            content = memory.content

        # Compute embedding
        embedding = await embedder.embed_query(content)

        # Dedupe: find nearest existing memory of same type
        dedupe_sql = text(
            """
            SELECT id, content, embedding <=> CAST(:emb AS vector) AS dist
            FROM memories
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND memory_type = :mtype
            ORDER BY embedding <=> CAST(:emb AS vector)
            LIMIT 1
            """
        )
        result = await db.execute(
            dedupe_sql,
            {
                "emb": str(embedding),
                "tenant_id": str(tenant_id),
                "user_id": str(user_id),
                "mtype": memory.memory_type,
            },
        )
        row = result.mappings().first()

        if row and row["dist"] < DEDUPE_THRESHOLD:
            # Update existing instead of duplicate
            existing = await db.get(Memory, row["id"])
            if existing:
                existing.content = content  # latest wins
                existing.embedding = embedding
                existing.updated_at = datetime.now(timezone.utc)
                logger.info("memory_deduped_updated", id=str(existing.id), dist=row["dist"])
                return existing

        # Insert new
        ttl_days = TTL_DAYS.get(memory.memory_type)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=ttl_days) if ttl_days else None
        )

        new_mem = Memory(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            memory_type=memory.memory_type,
            content=content,
            embedding=embedding,
            pinned=False,
            expires_at=expires_at,
            source_message_id=source_message_id,
        )
        db.add(new_mem)
        await db.flush()
        logger.info("memory_added", id=str(new_mem.id), type=memory.memory_type)
        return new_mem

    async def search(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        query: str,
        top_k: int = 5,
        memory_types: list[str] | None = None,
        min_similarity: float = 0.5,
    ) -> list[MemoryRecord]:
        """Semantic search over user's memories."""
        if not query.strip():
            return []

        emb = await embedder.embed_query(query)

        sql = """
            SELECT id, memory_type, content, pinned, expires_at, created_at,
                   embedding <=> CAST(:emb AS vector) AS dist
            FROM memories
            WHERE tenant_id = :tenant_id
              AND user_id = :user_id
              AND (expires_at IS NULL OR expires_at > NOW())
        """
        params = {
            "emb": str(emb),
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
            "top_k": top_k,
        }
        if memory_types:
            sql += " AND memory_type = ANY(:mtypes)"
            params["mtypes"] = memory_types  # type: ignore[assignment]
        sql += " ORDER BY embedding <=> CAST(:emb AS vector) LIMIT :top_k"

        result = await db.execute(text(sql), params)
        rows = result.mappings().all()

        records: list[MemoryRecord] = []
        for row in rows:
            if 1 - row["dist"] < min_similarity:
                continue
            records.append(
                MemoryRecord(
                    id=row["id"],
                    memory_type=row["memory_type"],
                    content=row["content"],
                    pinned=row["pinned"],
                    expires_at=row["expires_at"],
                    created_at=row["created_at"],
                )
            )
        return records

    async def list_by_user(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        memory_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        """List memories for management UI."""
        stmt = select(Memory).where(
            Memory.tenant_id == tenant_id,
            Memory.user_id == user_id,
        )
        if memory_type:
            stmt = stmt.where(Memory.memory_type == memory_type)
        stmt = (
            stmt.order_by(Memory.pinned.desc(), Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return [MemoryRecord.from_model(m) for m in result.scalars().all()]

    async def update_content(
        self,
        db: AsyncSession,
        memory_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        new_content: str,
        pinned: bool | None = None,
    ) -> Memory | None:
        """Edit a memory's content. Re-embeds."""
        result = await db.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.tenant_id == tenant_id,
                Memory.user_id == user_id,
            )
        )
        mem = result.scalar_one_or_none()
        if not mem:
            return None

        mem.content = new_content
        mem.embedding = await embedder.embed_query(new_content)
        if pinned is not None:
            mem.pinned = pinned
        await db.flush()
        return mem

    async def delete_one(
        self,
        db: AsyncSession,
        memory_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
    ) -> bool:
        result = await db.execute(
            delete(Memory).where(
                Memory.id == memory_id,
                Memory.tenant_id == tenant_id,
                Memory.user_id == user_id,
            )
        )
        return (result.rowcount or 0) > 0

    async def delete_all_for_user(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
    ) -> int:
        """GDPR right to be forgotten."""
        result = await db.execute(
            delete(Memory).where(
                Memory.tenant_id == tenant_id,
                Memory.user_id == user_id,
            )
        )
        return result.rowcount or 0

    async def cleanup_expired(self, db: AsyncSession) -> int:
        """Delete memories past their TTL. Run from Celery beat daily."""
        result = await db.execute(
            delete(Memory).where(
                Memory.expires_at.isnot(None),
                Memory.expires_at < datetime.now(timezone.utc),
                Memory.pinned == False,  # noqa: E712 — SQLAlchemy needs ==
            )
        )
        count = result.rowcount or 0
        logger.info("memory_cleanup", deleted=count)
        return count


memory_store = MemoryStore()
