"""Embedding service — wraps Gemini text-embedding-004 with batching + retry."""
import asyncio

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

genai.configure(api_key=settings.GOOGLE_API_KEY)

BATCH_SIZE = 100  # Gemini limit
MAX_PARALLEL = 5  # don't smash rate limits


class EmbeddingService:
    def __init__(self, model: str | None = None):
        self.model = model or settings.EMBEDDING_MODEL
        self._sem = asyncio.Semaphore(MAX_PARALLEL)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _embed_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        """Embed a batch — Gemini supports up to 100 per request."""
        async with self._sem:
            try:
                # google-generativeai is sync-only; run in executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: genai.embed_content(
                        model=f"models/{self.model}",
                        content=texts,
                        task_type=task_type,
                    ),
                )
                return result["embedding"]
            except Exception as e:
                logger.warning("embed_failed", error=str(e))
                raise LLMError(f"Embedding failed: {e}")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed for ingestion (task_type=RETRIEVAL_DOCUMENT)."""
        if not texts:
            return []
        return await self._embed_in_batches(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query (task_type=RETRIEVAL_QUERY)."""
        result = await self._embed_in_batches([text], "RETRIEVAL_QUERY")
        return result[0]

    async def _embed_in_batches(self, texts: list[str], task_type: str) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            result = await self._embed_batch(batch, task_type)
            embeddings.extend(result)
            logger.info("embedded_batch", count=len(batch), total_so_far=len(embeddings))
        return embeddings


embedder = EmbeddingService()
