"""RAG orchestrator — ties query rewriter, embedder, vector store, reranker, citation.

Public API used by the agent: `retrieve(query, tenant_id, collections) -> RagResult`.
"""
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.rag.citation import (
    Citation,
    chunks_to_citations,
    format_context_for_llm,
    format_source_list,
)
from app.rag.embedder import embedder
from app.rag.query_rewriter import rewrite_query_for_embedding
from app.rag.reranker import rerank
from app.rag.vector_store import RetrievedChunk, vector_store

logger = get_logger(__name__)


@dataclass
class RagResult:
    chunks: list[RetrievedChunk]
    citations: list[Citation]
    context_for_llm: str
    source_list: str  # Markdown footer

    @property
    def has_results(self) -> bool:
        return len(self.chunks) > 0


async def retrieve(
    db: AsyncSession,
    query: str,
    tenant_id: UUID,
    collections: Sequence[str],
    top_k_initial: int = 20,
    top_n_final: int = 5,
    use_hyde: bool = True,
    use_rerank: bool = True,
    min_similarity: float = 0.5,
) -> RagResult:
    """Full RAG retrieval flow.

    Steps:
      1. Rewrite query via HyDE (optional)
      2. Embed
      3. ANN search top-k from pgvector with ACL filter
      4. Rerank to top-n with cheap LLM (optional)
      5. Build citations + LLM context
    """
    if not query.strip() or not collections:
        return RagResult(chunks=[], citations=[], context_for_llm="", source_list="")

    # 1. Rewrite
    embed_input = await rewrite_query_for_embedding(query, use_hyde=use_hyde)

    # 2. Embed
    query_emb = await embedder.embed_query(embed_input)

    # 3. ANN search
    candidates = await vector_store.search(
        db=db,
        embedding=query_emb,
        tenant_id=tenant_id,
        collections=collections,
        top_k=top_k_initial,
        min_similarity=min_similarity,
    )

    if not candidates:
        logger.info("rag_no_candidates", query=query[:80])
        return RagResult(chunks=[], citations=[], context_for_llm="", source_list="")

    # 4. Rerank
    if use_rerank and len(candidates) > top_n_final:
        final_chunks = await rerank(query, candidates, top_n=top_n_final)
    else:
        final_chunks = candidates[:top_n_final]

    # 5. Citations + context
    citations = chunks_to_citations(final_chunks)
    context = format_context_for_llm(final_chunks, citations)
    sources = format_source_list(citations)

    logger.info(
        "rag_retrieved",
        candidates=len(candidates),
        final=len(final_chunks),
        citations=len(citations),
    )

    return RagResult(
        chunks=final_chunks,
        citations=citations,
        context_for_llm=context,
        source_list=sources,
    )
