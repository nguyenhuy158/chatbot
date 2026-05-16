"""Eval runner — runs the golden dataset through the agent and aggregates results.

Designed to run:
  - Locally: `python -m app.eval.cli`
  - In CI: nightly via Celery beat (app.workers.scheduled.run_eval_suite)
  - On-demand: admin endpoint

Outputs a structured report (JSON) and optionally a Markdown summary.
"""
import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage

from app.agent.graph import agent_graph
from app.agent.state import AgentState
from app.core.config import settings
from app.core.logging import get_logger
from app.eval.dataset import GoldenItem, load_golden_dataset
from app.eval.metrics import evaluate_hard_checks

logger = get_logger(__name__)


@dataclass
class EvalResult:
    item_id: str
    category: str
    role: str
    lang: str
    query: str
    answer: str
    tools_used: list[str]
    passed: bool
    refused: bool
    keyword_hit: bool | None
    tool_match: bool | None
    latency_ms: int
    error: str | None = None


@dataclass
class EvalReport:
    started_at: str
    finished_at: str
    duration_seconds: float
    total: int
    passed: int
    failed: int
    by_category: dict[str, dict] = field(default_factory=dict)
    results: list[EvalResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


async def _run_single(
    item: GoldenItem,
    tenant_id: UUID,
    eval_user_id: UUID,
) -> EvalResult:
    """Run a single golden item through the agent."""
    state: AgentState = {
        "tenant_id": tenant_id,
        "user_id": eval_user_id,
        "role": item.role,  # type: ignore[typeddict-item]
        "lang": item.lang,
        "messages": [HumanMessage(content=item.query)],
        "iteration": 0,
        "metadata": {"is_eval": True},
    }

    started = time.perf_counter()
    try:
        final = await asyncio.wait_for(agent_graph.ainvoke(state), timeout=60.0)
        answer = final.get("final_answer", "")
        tool_results = final.get("tool_results", []) or []
        tools_used = [t.get("name", "") for t in tool_results if t.get("success")]
        duration_ms = int((time.perf_counter() - started) * 1000)

        checks = evaluate_hard_checks(item, answer, tools_used)
        return EvalResult(
            item_id=item.id,
            category=item.category,
            role=item.role,
            lang=item.lang,
            query=item.query,
            answer=answer,
            tools_used=tools_used,
            passed=checks["passed"],
            refused=checks["refused"],
            keyword_hit=checks["keyword_hit"],
            tool_match=checks["tool_match"],
            latency_ms=duration_ms,
        )
    except asyncio.TimeoutError:
        return EvalResult(
            item_id=item.id,
            category=item.category,
            role=item.role,
            lang=item.lang,
            query=item.query,
            answer="",
            tools_used=[],
            passed=False,
            refused=False,
            keyword_hit=False,
            tool_match=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error="timeout",
        )
    except Exception as e:
        logger.exception("eval_item_failed", item_id=item.id)
        return EvalResult(
            item_id=item.id,
            category=item.category,
            role=item.role,
            lang=item.lang,
            query=item.query,
            answer="",
            tools_used=[],
            passed=False,
            refused=False,
            keyword_hit=False,
            tool_match=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=str(e)[:500],
        )


async def run_eval_suite(
    items: list[GoldenItem] | None = None,
    concurrency: int = 4,
    tenant_id: UUID | None = None,
) -> EvalReport:
    """Run the full golden dataset (or a subset). Returns aggregated report."""
    if items is None:
        items = load_golden_dataset()
    if not items:
        raise ValueError("No golden items to evaluate")

    tenant_id = tenant_id or settings.DEFAULT_TENANT_ID
    eval_user_id = uuid4()  # synthetic user, won't be persisted via agent stubs

    started_at = datetime.now(timezone.utc)
    started_perf = time.perf_counter()
    sem = asyncio.Semaphore(concurrency)

    async def bounded(item: GoldenItem) -> EvalResult:
        async with sem:
            return await _run_single(item, tenant_id, eval_user_id)

    results = await asyncio.gather(*[bounded(it) for it in items])

    # Aggregate
    by_category: dict[str, dict] = {}
    for r in results:
        bucket = by_category.setdefault(r.category, {"total": 0, "passed": 0, "failed": 0})
        bucket["total"] += 1
        if r.passed:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1

    finished_at = datetime.now(timezone.utc)
    report = EvalReport(
        started_at=started_at.isoformat(),
        finished_at=finished_at.isoformat(),
        duration_seconds=round(time.perf_counter() - started_perf, 2),
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        failed=sum(1 for r in results if not r.passed),
        by_category=by_category,
        results=results,
    )
    logger.info(
        "eval_suite_complete",
        total=report.total,
        passed=report.passed,
        pass_rate=round(report.pass_rate * 100, 1),
        duration=report.duration_seconds,
    )
    return report


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    """Write JSON + Markdown summary to disk. Returns (json_path, md_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"eval_{ts}.json"
    json_path.write_text(
        json.dumps(
            {
                "started_at": report.started_at,
                "finished_at": report.finished_at,
                "duration_seconds": report.duration_seconds,
                "total": report.total,
                "passed": report.passed,
                "failed": report.failed,
                "pass_rate": report.pass_rate,
                "by_category": report.by_category,
                "results": [asdict(r) for r in report.results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    md_path = out_dir / f"eval_{ts}.md"
    md_path.write_text(_render_markdown(report), encoding="utf-8")

    return json_path, md_path


def _render_markdown(report: EvalReport) -> str:
    lines = [
        f"# Eval Report — {report.finished_at}",
        "",
        f"- Total: **{report.total}**",
        f"- Passed: **{report.passed}** ({report.pass_rate * 100:.1f}%)",
        f"- Failed: **{report.failed}**",
        f"- Duration: {report.duration_seconds}s",
        "",
        "## By Category",
        "",
        "| Category | Total | Passed | Failed | Pass rate |",
        "|---|---|---|---|---|",
    ]
    for cat, stats in sorted(report.by_category.items()):
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
        lines.append(f"| {cat} | {stats['total']} | {stats['passed']} | {stats['failed']} | {rate:.1f}% |")

    failed = [r for r in report.results if not r.passed]
    if failed:
        lines += ["", "## Failed Cases", ""]
        for r in failed:
            reason = []
            if r.error:
                reason.append(f"error={r.error}")
            if r.refused and not r.passed:
                reason.append("unexpected_refusal")
            if r.keyword_hit is False:
                reason.append("missing_keywords")
            if r.tool_match is False:
                reason.append(f"missing_tool")
            lines.append(f"- **{r.item_id}** ({r.category}, {r.lang}): {'; '.join(reason) or 'failed'}")
            lines.append(f"  - Q: {r.query}")
            lines.append(f"  - A: {r.answer[:200]}{'...' if len(r.answer) > 200 else ''}")

    return "\n".join(lines)
