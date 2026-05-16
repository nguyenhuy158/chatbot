"""Golden dataset loader. Reads YAML files under evals/golden/ into typed objects.

Format (per file):
  - id: unique
    category: faq|rag|memory|tools|guardrails|multilang
    role: external|internal
    lang: vi|en
    query: ...
    expected_keywords: [...]      # at least one must appear
    expected_refuses: false       # true if bot MUST refuse
    expected_uses_tool: null      # 'web_search', 'calculator', or null
    notes: optional
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml


GOLDEN_DIR = Path(__file__).resolve().parent.parent.parent / "evals" / "golden"


@dataclass
class GoldenItem:
    id: str
    category: Literal["faq", "rag", "memory", "tools", "guardrails", "multilang"]
    role: Literal["external", "internal"]
    lang: Literal["vi", "en"]
    query: str
    expected_keywords: list[str] = field(default_factory=list)
    expected_refuses: bool = False
    expected_uses_tool: str | None = None
    notes: str = ""


def load_golden_dataset(path: Path | None = None) -> list[GoldenItem]:
    """Load all .yaml files in the golden dir. Each file = list of items."""
    root = path or GOLDEN_DIR
    items: list[GoldenItem] = []
    seen_ids: set[str] = set()

    for yml in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        data = yaml.safe_load(yml.read_text(encoding="utf-8")) or []
        for raw in data:
            item = GoldenItem(
                id=raw["id"],
                category=raw["category"],
                role=raw.get("role", "external"),
                lang=raw.get("lang", "vi"),
                query=raw["query"],
                expected_keywords=raw.get("expected_keywords", []),
                expected_refuses=raw.get("expected_refuses", False),
                expected_uses_tool=raw.get("expected_uses_tool"),
                notes=raw.get("notes", ""),
            )
            if item.id in seen_ids:
                raise ValueError(f"Duplicate golden id: {item.id}")
            seen_ids.add(item.id)
            items.append(item)

    return items
