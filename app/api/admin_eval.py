"""Admin endpoints for eval suite — trigger run, fetch latest report."""
import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.core.deps import AdminUser
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

REPORT_DIR = Path("/tmp/eval-reports")


class EvalRunRequest(BaseModel):
    categories: list[str] | None = None
    concurrency: int = 2


@router.post("/admin/eval/run")
async def trigger_eval(
    req: EvalRunRequest, admin: AdminUser, background: BackgroundTasks
) -> dict:
    """Kick off eval suite in background. Returns immediately."""

    async def _run():
        from app.eval.dataset import load_golden_dataset
        from app.eval.runner import run_eval_suite, write_report

        items = load_golden_dataset()
        if req.categories:
            items = [i for i in items if i.category in req.categories]
        report = await run_eval_suite(items=items, concurrency=req.concurrency)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        write_report(report, REPORT_DIR)
        logger.info(
            "eval_admin_trigger_complete",
            passed=report.passed,
            total=report.total,
            pass_rate=report.pass_rate,
        )

    background.add_task(_run)
    return {"status": "started", "categories": req.categories or "all"}


@router.get("/admin/eval/latest")
async def latest_report(admin: AdminUser) -> dict:
    """Return the most recent eval JSON report."""
    if not REPORT_DIR.exists():
        raise NotFoundError("No reports yet — trigger /admin/eval/run first")

    reports = sorted(REPORT_DIR.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        raise NotFoundError("No reports found")

    latest = reports[0]
    return json.loads(latest.read_text(encoding="utf-8"))


@router.get("/admin/eval/reports")
async def list_reports(admin: AdminUser, limit: int = 10) -> list[dict]:
    """List recent reports (metadata only)."""
    if not REPORT_DIR.exists():
        return []

    reports = sorted(REPORT_DIR.glob("eval_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for r in reports[:limit]:
        try:
            data = json.loads(r.read_text(encoding="utf-8"))
            out.append({
                "file": r.name,
                "finished_at": data.get("finished_at"),
                "total": data.get("total"),
                "passed": data.get("passed"),
                "pass_rate": data.get("pass_rate"),
            })
        except Exception:
            continue
    return out
