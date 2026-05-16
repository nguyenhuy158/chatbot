"""Vector store — thin wrapper over pgvector for our schema.

ACL is enforced at query time via WHERE clauses (NOT post-filter).
"""
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import Chunk, Document

logger = get_logger(__name__)


@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    content: str
    page: int | None
    source_url: str | None
    collection: str
    distance: float  # cosine distance, lower = more similar
    metadata: dict


class VectorStore:
    """ACL-aware pgvector operations."""

    async def search(
        self,
        db: AsyncSession,
        embedding: list[float],
        tenant_id: UUID,
        collections: Sequence[str],
        top_k: int = 20,
        min_similarity: float = 0.0,
    ) -> list[RetrievedChunk]:
        """Cosine similarity search with ACL filter baked in.

        Returns chunks with distance (0 = identical, 2 = opposite).
        """
        if not collections:
            return []

        # pgvector cosine distance operator: <=>
        # We hit the HNSW index by ordering by `<=>` and limiting.
        sql = text(
            """
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.content,
                c.metadata AS chunk_metadata,
                c.embedding <=> CAST(:embedding AS vector) AS distance,
                d.title AS document_title,
                d.source_url,
                d.collection
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.tenant_id = :tenant_id
              AND d.tenant_id = :tenant_id
              AND d.collection = ANY(:collections)
              AND d.status = 'approved'
            ORDER BY c.embedding <=> CAST(:embedding AS vector)
            LIMIT :top_k
            """
        )

        result = await db.execute(
            sql,
            {
                "embedding": str(embedding),
                "tenant_id": str(tenant_id),
                "collections": list(collections),
                "top_k": top_k,
            },
        )
        rows = result.mappings().all()

        chunks: list[RetrievedChunk] = []
        for row in rows:
            if 1 - row["distance"] < min_similarity:
                continue
            meta = row["chunk_metadata"] or {}
            chunks.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    document_title=row["document_title"],
                    content=row["content"],
                    page=meta.get("page"),
                    source_url=row["source_url"],
                    collection=row["collection"],
                    distance=row["distance"],
                    metadata=meta,
                )
            )

        logger.info("vector_search", returned=len(chunks), top_k=top_k)
        return chunks

    async def insert_chunks(
        self,
        db: AsyncSession,
        document_id: UUID,
        tenant_id: UUID,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """Bulk insert chunks with embeddings."""
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")

        for chunk, emb in zip(chunks, embeddings, strict=True):
            chunk.document_id = document_id
            chunk.tenant_id = tenant_id
            chunk.embedding = emb
            db.add(chunk)
        await db.flush()
        return len(chunks)

    async def delete_document_chunks(
        self, db: AsyncSession, document_id: UUID, tenant_id: UUID
    ) -> int:
        """Delete all chunks for a document. ON DELETE CASCADE also handles this,
        but explicit is useful when re-indexing."""
        result = await db.execute(
            text(
                "DELETE FROM chunks WHERE document_id = :doc_id AND tenant_id = :tenant_id"
            ),
            {"doc_id": str(document_id), "tenant_id": str(tenant_id)},
        )
        return result.rowcount or 0


vector_store = VectorStore()
