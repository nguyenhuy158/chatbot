"""Scheduled Celery tasks."""
import asyncio

from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.memory import memory_store
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task
def cleanup_expired_memories() -> int:
    """Delete memories past expires_at."""
    return asyncio.run(_cleanup_expired_memories_async())


async def _cleanup_expired_memories_async() -> int:
    async with AsyncSessionLocal() as db:
        count = await memory_store.cleanup_expired(db)
        await db.commit()
        return count


@celery_app.task
def send_cost_report() -> str:
    """Daily cost report email to admins."""
    import asyncio
    return asyncio.run(_send_cost_report_async())


async def _send_cost_report_async() -> str:
    from app.analytics import format_daily_cost_email, queries, send_email
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        report = await queries.daily_cost_report(db, settings.DEFAULT_TENANT_ID)

    msg = format_daily_cost_email(report)
    if not msg.to:
        logger.info("cost_report_no_recipients")
        return "skipped"

    ok = await send_email(msg)
    return "sent" if ok else "logged_only"


@celery_app.task
def scan_stale_documents() -> int:
    """Find docs not updated >180d. Phase 2 follow-up."""
    logger.info("scan_stale_documents")
    return 0


@celery_app.task
def cleanup_stale_images() -> int:
    """Delete uploaded images older than 24h. Phase 9."""
    from app.multimodal import cleanup_stale

    deleted = cleanup_stale(older_than_hours=24)
    logger.info("image_cleanup", deleted=deleted)
    return deleted


@celery_app.task
def run_eval_suite() -> dict:
    """Nightly eval. Writes report to /tmp/eval-reports/. Phase 6."""
    import asyncio
    from pathlib import Path

    from app.eval.runner import run_eval_suite as _run, write_report

    report = asyncio.run(_run(concurrency=2))
    out_dir = Path("/tmp/eval-reports")
    write_report(report, out_dir)
    return {
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "duration_seconds": report.duration_seconds,
    }
    import asyncio
    from pathlib import Path

    from app.eval.runner import run_eval_suite as _run, write_report

    report = asyncio.run(_run(concurrency=2))
    out_dir = Path("/tmp/eval-reports")
    write_report(report, out_dir)
    return {
        "passed": report.passed,
        "total": report.total,
        "pass_rate": report.pass_rate,
        "duration_seconds": report.duration_seconds,
    }
