"""Document upload + management endpoints.

Flow: upload → save to disk (or Azure Blob) → enqueue Celery ingestion task →
return doc id immediately. User polls status or sees in admin panel.
"""
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.deps import DbSession, User
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.logging import get_logger
from app.db.models import Document
from app.db.session import AsyncSessionLocal
from app.rag import ingest_file, reindex_document, vector_store

router = APIRouter()
logger = get_logger(__name__)

ALLOWED_EXT = {".pdf", ".docx", ".md", ".txt", ".html"}
UPLOAD_DIR = Path("/tmp/chatbot-uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


class DocumentOut(BaseModel):
    id: UUID
    title: str | None
    collection: str
    file_type: str | None
    status: str
    version: int
    source_url: str | None
    owner_email: str | None

    class Config:
        from_attributes = True


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    user: User,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    collection: str = Form(...),
    source_url: str | None = Form(None),
) -> DocumentOut:
    """Upload a document and ingest it asynchronously."""
    if not user.is_internal:
        raise ForbiddenError("Only internal users can upload documents")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXT:
        raise ValueError(f"Unsupported extension: {suffix}. Allowed: {ALLOWED_EXT}")

    # External users restricted to public_docs / faq
    if collection not in {"public_docs", "faq", "internal_sop"}:
        raise ValueError(f"Unknown collection: {collection}")

    # Persist file to upload dir (in prod: stream to Azure Blob)
    tmp_path = Path(tempfile.mktemp(suffix=suffix, dir=UPLOAD_DIR))
    with tmp_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    logger.info("file_saved", path=str(tmp_path), size=tmp_path.stat().st_size)

    # Ingest in background (small docs only; large ones should go through Celery)
    background.add_task(
        _run_ingest,
        path=tmp_path,
        tenant_id=user.tenant_id,
        collection=collection,
        owner_email=None,  # populate from user record in future
        source_url=source_url,
    )

    # Return placeholder; actual doc record created during ingestion
    return DocumentOut(
        id=UUID("00000000-0000-0000-0000-000000000000"),
        title=file.filename,
        collection=collection,
        file_type=suffix.lstrip("."),
        status="ingesting",
        version=0,
        source_url=source_url,
        owner_email=None,
    )


async def _run_ingest(
    path: Path,
    tenant_id: UUID,
    collection: str,
    owner_email: str | None,
    source_url: str | None,
) -> None:
    """Background ingestion runner — owns its own DB session."""
    try:
        async with AsyncSessionLocal() as db:
            doc = await ingest_file(
                db=db,
                path=path,
                tenant_id=tenant_id,
                collection=collection,
                owner_email=owner_email,
                source_url=source_url,
            )
            await db.commit()
            logger.info("ingest_bg_complete", doc_id=str(doc.id))
    except Exception as e:
        logger.exception("ingest_bg_failed", error=str(e))


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    user: User,
    db: DbSession,
    collection: str | None = None,
) -> list[DocumentOut]:
    """List documents accessible to the user."""
    query = select(Document).where(Document.tenant_id == user.tenant_id)
    if collection:
        query = query.where(Document.collection == collection)
    if not user.is_internal:
        query = query.where(Document.collection.in_(["public_docs", "faq"]))
    query = query.order_by(Document.created_at.desc()).limit(100)

    result = await db.execute(query)
    return [DocumentOut.model_validate(d) for d in result.scalars().all()]


@router.delete("/{document_id}", status_code=204)
async def delete_document(document_id: UUID, user: User, db: DbSession) -> None:
    if not user.is_internal:
        raise ForbiddenError("Only internal users can delete documents")

    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise NotFoundError("Document not found")

    await db.execute(delete(Document).where(Document.id == document_id))


@router.post("/{document_id}/reindex")
async def reindex(document_id: UUID, user: User, db: DbSession) -> dict:
    if not user.is_internal:
        raise ForbiddenError("Only internal users can reindex")
    count = await reindex_document(db, document_id, user.tenant_id)
    return {"document_id": str(document_id), "chunks_indexed": count}
