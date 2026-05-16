"""Citation builder — format retrieved chunks into inline citations + source list."""
from dataclasses import asdict, dataclass

from app.rag.vector_store import RetrievedChunk


@dataclass
class Citation:
    index: int  # 1-based
    document_title: str
    page: int | None
    source_url: str | None
    collection: str
    confidence: float  # 0-1, derived from distance

    def to_dict(self) -> dict:
        return asdict(self)


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Convert chunks to citation entries. Deduplicates by (document_id, page)."""
    seen: set[tuple] = set()
    citations: list[Citation] = []

    for chunk in chunks:
        key = (chunk.document_id, chunk.page)
        if key in seen:
            continue
        seen.add(key)
        # Cosine distance to similarity: 1 - distance, clamped
        similarity = max(0.0, min(1.0, 1.0 - chunk.distance))
        citations.append(
            Citation(
                index=len(citations) + 1,
                document_title=chunk.document_title,
                page=chunk.page,
                source_url=chunk.source_url,
                collection=chunk.collection,
                confidence=round(similarity, 3),
            )
        )

    return citations


def format_context_for_llm(chunks: list[RetrievedChunk], citations: list[Citation]) -> str:
    """Format chunks as a context block the LLM can cite from.

    Maps chunks to citation indices using (document_id, page).
    """
    # Build (doc_id, page) -> index map
    citation_index: dict[tuple, int] = {}
    for cit in citations:
        # Find matching chunk by title+page since citation has no doc_id directly
        for chunk in chunks:
            if (
                chunk.document_title == cit.document_title
                and chunk.page == cit.page
            ):
                citation_index[(chunk.document_id, chunk.page)] = cit.index
                break

    parts: list[str] = []
    for chunk in chunks:
        idx = citation_index.get((chunk.document_id, chunk.page), 0)
        page_str = f" (p.{chunk.page})" if chunk.page else ""
        parts.append(f"[{idx}] {chunk.document_title}{page_str}:\n{chunk.content}")

    return "\n\n---\n\n".join(parts)


def format_source_list(citations: list[Citation]) -> str:
    """Render the 'Nguồn' / 'Sources' footer for the user-facing reply."""
    if not citations:
        return ""

    lines = ["**Nguồn:**"]
    for cit in citations:
        page_str = f" (trang {cit.page})" if cit.page else ""
        url_str = f" — {cit.source_url}" if cit.source_url else ""
        confidence_icon = "🟢" if cit.confidence > 0.75 else "🟡" if cit.confidence > 0.5 else "🔴"
        lines.append(f"[{cit.index}] {confidence_icon} {cit.document_title}{page_str}{url_str}")
    return "\n".join(lines)
