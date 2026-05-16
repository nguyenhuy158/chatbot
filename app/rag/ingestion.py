"""Document ingestion pipeline.

Flow: parse → chunk → embed → store. Idempotent via file_hash.
Designed to run inside Celery for large docs, or inline for small ones.
"""
import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Chunk as ChunkModel
from app.db.models import Document
from app.rag.chunker import chunk_document
from app.rag.embedder import embedder
from app.rag.parser import parse
from app.rag.vector_store import vector_store

logger = get_logger(__name__)


def compute_file_hash(path: Path) -> str:
    """SHA-256 of file content for dedupe."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


async def ingest_file(
    db: AsyncSession,
    path: Path,
    tenant_id: UUID,
    collection: str,
    owner_email: str | None = None,
    source_url: str | None = None,
    acl: dict | None = None,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
) -> Document:
    """Parse + chunk + embed + store a single file.

    Returns the Document (created or existing if hash matches).
    """
    file_hash = compute_file_hash(path)

    # Dedupe by hash within tenant + collection
    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.collection == collection,
            Document.file_hash == file_hash,
        )
    )
    existing_doc = existing.scalar_one_or_none()
    if existing_doc:
        logger.info("ingest_skip_existing", doc_id=str(existing_doc.id), hash=file_hash)
        return existing_doc

    # Parse
    parsed = parse(path)

    # Create document row
    doc = Document(
        id=uuid4(),
        tenant_id=tenant_id,
        collection=collection,
        title=parsed.title or path.name,
        source_url=source_url,
        storage_path=str(path),
        file_type=path.suffix.lower().lstrip("."),
        file_hash=file_hash,
        owner_email=owner_email,
        acl=acl,
        doc_metadata=parsed.metadata,
        status="approved",
        version=1,
    )
    db.add(doc)
    await db.flush()

    # Chunk
    chunks = chunk_document(parsed, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
    if not chunks:
        logger.warning("ingest_no_chunks", doc_id=str(doc.id))
        return doc

    # Embed in batch
    texts = [c.text for c in chunks]
    embeddings = await embedder.embed_documents(texts)

    # Persist chunks
    chunk_models = [
        ChunkModel(
            id=uuid4(),
            tenant_id=tenant_id,
            document_id=doc.id,
            content=c.text,
            chunk_index=c.chunk_index,
            chunk_metadata=c.metadata,
        )
        for c in chunks
    ]
    await vector_store.insert_chunks(
        db=db,
        document_id=doc.id,
        tenant_id=tenant_id,
        chunks=chunk_models,
        embeddings=embeddings,
    )

    logger.info(
        "ingest_complete",
        doc_id=str(doc.id),
        title=doc.title,
        chunks=len(chunks),
    )
    return doc


async def reindex_document(
    db: AsyncSession,
    document_id: UUID,
    tenant_id: UUID,
) -> int:
    """Re-chunk and re-embed an existing document. Returns chunk count."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.storage_path:
        raise ValueError(f"Document {document_id} not found or no storage_path")

    # Drop old chunks
    await vector_store.delete_document_chunks(db, document_id, tenant_id)

    # Re-parse + re-chunk + re-embed
    parsed = parse(Path(doc.storage_path))
    chunks = chunk_document(parsed)
    embeddings = await embedder.embed_documents([c.text for c in chunks])

    chunk_models = [
        ChunkModel(
            id=uuid4(),
            tenant_id=tenant_id,
            document_id=doc.id,
            content=c.text,
            chunk_index=c.chunk_index,
            chunk_metadata=c.metadata,
        )
        for c in chunks
    ]
    await vector_store.insert_chunks(
        db=db,
        document_id=doc.id,
        tenant_id=tenant_id,
        chunks=chunk_models,
        embeddings=embeddings,
    )

    doc.version += 1
    await db.flush()

    return len(chunks)
