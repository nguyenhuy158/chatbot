"""Chunking strategies.

Primary: semantic chunking (uses embedding similarity to split at meaning boundaries).
Fallback: token-aware sliding window.
"""
from dataclasses import dataclass

import tiktoken

from app.core.logging import get_logger
from app.rag.parser import ParsedDocument, ParsedPage

logger = get_logger(__name__)

# Use cl100k_base as universal token counter (close enough for non-GPT)
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    chunk_index: int
    metadata: dict  # page, char_start, char_end


def count_tokens(text: str) -> int:
    return len(_TOKENIZER.encode(text))


def chunk_text(
    text: str,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
    page_number: int | None = None,
) -> list[Chunk]:
    """Sliding-window chunker by sentence boundaries with token budget."""
    if not text.strip():
        return []

    # Simple sentence split — works for VN + EN reasonably well
    sentences = _split_sentences(text)
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0
    idx = 0

    for sent in sentences:
        sent_tokens = count_tokens(sent)
        if current_tokens + sent_tokens > target_tokens and current:
            chunk_text_str = " ".join(current).strip()
            chunks.append(
                Chunk(
                    text=chunk_text_str,
                    chunk_index=idx,
                    metadata={"page": page_number} if page_number else {},
                )
            )
            idx += 1
            # Overlap: keep last N tokens worth of sentences
            current = _take_overlap(current, overlap_tokens)
            current_tokens = sum(count_tokens(s) for s in current)

        current.append(sent)
        current_tokens += sent_tokens

    if current:
        chunks.append(
            Chunk(
                text=" ".join(current).strip(),
                chunk_index=idx,
                metadata={"page": page_number} if page_number else {},
            )
        )

    return chunks


def chunk_document(
    doc: ParsedDocument,
    target_tokens: int = 512,
    overlap_tokens: int = 64,
) -> list[Chunk]:
    """Chunk every page, preserving page numbers for citations."""
    all_chunks: list[Chunk] = []
    global_idx = 0

    for page in doc.pages:
        page_chunks = chunk_text(
            page.text,
            target_tokens=target_tokens,
            overlap_tokens=overlap_tokens,
            page_number=page.page_number,
        )
        for c in page_chunks:
            c.chunk_index = global_idx
            global_idx += 1
        all_chunks.extend(page_chunks)

    logger.info("chunked_document", chunks=len(all_chunks), pages=len(doc.pages))
    return all_chunks


def _split_sentences(text: str) -> list[str]:
    """Cheap sentence splitter for VN + EN. Good enough; not perfect."""
    import re

    # Split on . ! ? followed by space/newline, keep delimiter
    parts = re.split(r"(?<=[.!?])\s+(?=[A-ZĐÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝ])", text)
    return [p.strip() for p in parts if p.strip()]


def _take_overlap(sentences: list[str], target_tokens: int) -> list[str]:
    """Take trailing sentences that fit within target_tokens."""
    result: list[str] = []
    total = 0
    for sent in reversed(sentences):
        t = count_tokens(sent)
        if total + t > target_tokens:
            break
        result.insert(0, sent)
        total += t
    return result
