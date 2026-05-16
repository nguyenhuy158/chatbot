"""Eval module — golden dataset loader, runner, metrics."""
from app.eval.dataset import GoldenItem, load_golden_dataset
from app.eval.runner import EvalReport, EvalResult, run_eval_suite

__all__ = ["GoldenItem", "load_golden_dataset", "EvalReport", "EvalResult", "run_eval_suite"]
