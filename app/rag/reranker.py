"""Reranker — rerank top-k candidates using a cross-encoder or LLM.

For MVP we use an LLM-based reranker (cheap, no extra model to host).
Production: swap to BGE-reranker self-hosted for speed.
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import get_logger
from app.rag.vector_store import RetrievedChunk
from app.services.llm_gateway import llm_gateway

logger = get_logger(__name__)

RERANK_SYSTEM = """You are a relevance ranker. Given a query and a list of passages, score each passage from 0 (irrelevant) to 10 (highly relevant) for answering the query.

Output ONLY valid JSON: {"scores": [<int>, <int>, ...]} with one score per passage in the same order. No explanation."""


async def rerank(
    query: str,
    chunks: list[RetrievedChunk],
    top_n: int = 5,
) -> list[RetrievedChunk]:
    """Rerank chunks using a cheap LLM and return top_n."""
    if not chunks:
        return []
    if len(chunks) <= top_n:
        return chunks

    # Build passages with index
    passages = "\n\n".join(
        f"[{i}] {c.content[:500]}" for i, c in enumerate(chunks)
    )

    user_msg = f"Query: {query}\n\nPassages:\n{passages}"

    try:
        response = await llm_gateway.invoke(
            [SystemMessage(content=RERANK_SYSTEM), HumanMessage(content=user_msg)],
            tier="cheap",
        )
        content = str(response.content).strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        scores: list[int] = data.get("scores", [])

        if len(scores) != len(chunks):
            logger.warning("rerank_score_mismatch", expected=len(chunks), got=len(scores))
            return chunks[:top_n]

        # Pair, sort by score desc, take top_n
        ranked = sorted(zip(chunks, scores, strict=True), key=lambda x: x[1], reverse=True)
        result = [c for c, _ in ranked[:top_n]]
        logger.info("reranked", input=len(chunks), output=len(result))
        return result
    except Exception as e:
        logger.warning("rerank_failed_fallback", error=str(e))
        # Fall back to top by vector distance
        return chunks[:top_n]
