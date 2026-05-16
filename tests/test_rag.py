"""Phase 2 unit tests — chunking, citation formatting, query rewriter.

Integration tests (real DB + real embedding) live under tests/integration/
and are skipped by default unless RUN_INTEGRATION=1.
"""
import os

import pytest

from app.rag.chunker import chunk_text, count_tokens
from app.rag.citation import (
    Citation,
    chunks_to_citations,
    format_source_list,
)
from app.rag.vector_store import RetrievedChunk
from uuid import uuid4


def test_count_tokens() -> None:
    assert count_tokens("") == 0
    assert count_tokens("hello world") > 0
    assert count_tokens("xin chào việt nam") > 0


def test_chunk_text_short_input_returns_single() -> None:
    chunks = chunk_text("This is a short text. Nothing more.", target_tokens=512)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_splits_long_input() -> None:
    # Build text with ~2000 tokens worth of sentences
    long_text = ". ".join([f"Sentence number {i} contains some content" for i in range(200)])
    chunks = chunk_text(long_text, target_tokens=200, overlap_tokens=20)
    assert len(chunks) > 1
    # Indices should be sequential
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_chunks_to_citations_dedupes() -> None:
    doc_id = uuid4()
    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_title="Test Doc",
            content="passage 1",
            page=1,
            source_url="https://example.com",
            collection="faq",
            distance=0.1,
            metadata={"page": 1},
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=doc_id,
            document_title="Test Doc",
            content="passage 2 same page",
            page=1,
            source_url="https://example.com",
            collection="faq",
            distance=0.2,
            metadata={"page": 1},
        ),
    ]
    citations = chunks_to_citations(chunks)
    # Same (doc_id, page) => single citation
    assert len(citations) == 1
    assert citations[0].index == 1
    assert citations[0].confidence > 0


def test_format_source_list_empty_returns_empty_string() -> None:
    assert format_source_list([]) == ""


def test_format_source_list_renders_markdown() -> None:
    citations = [
        Citation(
            index=1,
            document_title="SOP",
            page=12,
            source_url=None,
            collection="internal_sop",
            confidence=0.9,
        )
    ]
    out = format_source_list(citations)
    assert "**Nguồn:**" in out
    assert "SOP" in out
    assert "trang 12" in out


@pytest.mark.skipif(
    os.environ.get("RUN_INTEGRATION") != "1",
    reason="Integration test requires DB + GOOGLE_API_KEY",
)
@pytest.mark.asyncio
async def test_embed_query_returns_vector() -> None:
    from app.rag.embedder import embedder

    vec = await embedder.embed_query("xin chào")
    assert isinstance(vec, list)
    assert len(vec) == 768
