"""CLI for running the eval suite locally.

Usage:
    uv run python -m app.eval.cli --concurrency 4 --category faq tools
    uv run python -m app.eval.cli --out evals/reports
"""
import argparse
import asyncio
from pathlib import Path

from app.eval.dataset import load_golden_dataset
from app.eval.runner import run_eval_suite, write_report


async def main(args: argparse.Namespace) -> int:
    items = load_golden_dataset()
    if args.category:
        items = [i for i in items if i.category in args.category]
    if args.lang:
        items = [i for i in items if i.lang == args.lang]
    if not items:
        print("No items match the filters.")
        return 1

    print(f"Running {len(items)} items, concurrency={args.concurrency}")
    report = await run_eval_suite(items=items, concurrency=args.concurrency)

    print(f"\nPassed {report.passed}/{report.total} ({report.pass_rate * 100:.1f}%)")
    for cat, stats in sorted(report.by_category.items()):
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
        print(f"  {cat:15s}: {stats['passed']:>3d}/{stats['total']:<3d} ({rate:.0f}%)")

    if args.out:
        json_path, md_path = write_report(report, Path(args.out))
        print(f"\nReport written to:\n  {json_path}\n  {md_path}")

    # CI exit code — fail if below threshold
    return 0 if report.pass_rate >= args.threshold else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--category", nargs="+", help="Filter by category")
    parser.add_argument("--lang", choices=["vi", "en"], help="Filter by language")
    parser.add_argument("--out", default="evals/reports", help="Output dir for reports")
    parser.add_argument("--threshold", type=float, default=0.70, help="Min pass rate for exit 0")
    args = parser.parse_args()

    rc = asyncio.run(main(args))
    raise SystemExit(rc)
