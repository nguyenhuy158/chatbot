"""Query rewriting — HyDE (Hypothetical Document Embeddings).

Idea: instead of embedding the question directly, ask an LLM to write a hypothetical
answer first, then embed THAT. The hypothetical answer lives in the same semantic
space as real documents, so retrieval is more accurate.

Trade-off: +1 cheap LLM call per query, but recall typically jumps 10-20%.
Can be disabled via flag for latency-sensitive paths.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import get_logger
from app.services.llm_gateway import llm_gateway

logger = get_logger(__name__)

HYDE_SYSTEM = """You are a helpful assistant. Given a user question, write a short hypothetical answer (2-3 sentences) as if you were quoting from an authoritative document. Use the same language as the question. Be specific. Do not say "I don't know" or refuse — just write a plausible answer that would appear in a relevant document."""


async def rewrite_query_hyde(query: str) -> str:
    """Generate a hypothetical answer to use for embedding."""
    try:
        response = await llm_gateway.invoke(
            [SystemMessage(content=HYDE_SYSTEM), HumanMessage(content=query)],
            tier="cheap",
        )
        hyde = str(response.content).strip()
        logger.info("hyde_generated", query_len=len(query), hyde_len=len(hyde))
        return hyde
    except Exception as e:
        logger.warning("hyde_failed_fallback", error=str(e))
        return query  # fall back to raw query


async def rewrite_query_for_embedding(query: str, use_hyde: bool = True) -> str:
    """Public entry point — produces the string to embed for retrieval."""
    if use_hyde:
        return await rewrite_query_hyde(query)
    return query
