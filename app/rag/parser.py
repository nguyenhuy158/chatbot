"""Document parsers — extract structured text from various formats.

Uses pymupdf4llm for PDFs (best Markdown preservation) and unstructured for
DOCX/HTML. Returns dicts with text + per-page metadata for citation.
"""
from dataclasses import dataclass
from pathlib import Path

import pymupdf4llm

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedPage:
    page_number: int
    text: str
    metadata: dict


@dataclass
class ParsedDocument:
    pages: list[ParsedPage]
    title: str | None
    full_text: str
    metadata: dict


def parse_pdf(path: Path) -> ParsedDocument:
    """Parse PDF with page-level granularity for citations."""
    logger.info("parse_pdf", path=str(path))
    pages_data = pymupdf4llm.to_markdown(str(path), page_chunks=True)

    pages: list[ParsedPage] = []
    full_text_parts: list[str] = []

    for idx, page_data in enumerate(pages_data, start=1):
        text = page_data.get("text", "") if isinstance(page_data, dict) else str(page_data)
        if not text.strip():
            continue
        pages.append(
            ParsedPage(
                page_number=idx,
                text=text,
                metadata={"page": idx},
            )
        )
        full_text_parts.append(text)

    return ParsedDocument(
        pages=pages,
        title=path.stem,
        full_text="\n\n".join(full_text_parts),
        metadata={"page_count": len(pages)},
    )


def parse_docx(path: Path) -> ParsedDocument:
    """Parse DOCX via unstructured."""
    from unstructured.partition.docx import partition_docx

    logger.info("parse_docx", path=str(path))
    elements = partition_docx(filename=str(path))
    text = "\n\n".join(str(el) for el in elements if str(el).strip())
    return ParsedDocument(
        pages=[ParsedPage(page_number=1, text=text, metadata={})],
        title=path.stem,
        full_text=text,
        metadata={"element_count": len(elements)},
    )


def parse_markdown(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8")
    return ParsedDocument(
        pages=[ParsedPage(page_number=1, text=text, metadata={})],
        title=path.stem,
        full_text=text,
        metadata={},
    )


def parse_html(path: Path) -> ParsedDocument:
    from unstructured.partition.html import partition_html

    elements = partition_html(filename=str(path))
    text = "\n\n".join(str(el) for el in elements if str(el).strip())
    return ParsedDocument(
        pages=[ParsedPage(page_number=1, text=text, metadata={})],
        title=path.stem,
        full_text=text,
        metadata={},
    )


PARSERS = {
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".md": parse_markdown,
    ".markdown": parse_markdown,
    ".html": parse_html,
    ".htm": parse_html,
    ".txt": parse_markdown,
}


def parse(path: Path) -> ParsedDocument:
    """Dispatch to appropriate parser based on extension."""
    ext = path.suffix.lower()
    parser = PARSERS.get(ext)
    if not parser:
        raise ValueError(f"Unsupported file type: {ext}")
    return parser(path)
