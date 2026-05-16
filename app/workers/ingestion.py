"""Document ingestion tasks (Phase 2)."""
from app.core.logging import get_logger
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task
def ingest_document(document_id: str) -> dict:
    """Parse, chunk, embed, store. TODO Phase 2."""
    logger.info("ingest_document", document_id=document_id)
    return {"status": "stub", "document_id": document_id}
