"""LLM Gateway: tier routing + failover."""
from collections.abc import AsyncIterator
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import LLMError
from app.core.logging import get_logger

logger = get_logger(__name__)

Tier = Literal["cheap", "main", "hard"]


class LLMGateway:
    """Gateway with tier selection, retry, and failover."""

    def __init__(self):
        self._models: dict[Tier, list[BaseChatModel]] = {
            "cheap": [
                ChatGoogleGenerativeAI(
                    model=settings.LLM_CHEAP_MODEL,
                    google_api_key=settings.GOOGLE_API_KEY,
                    max_output_tokens=settings.LLM_MAX_TOKENS,
                ),
            ],
            "main": [
                ChatAnthropic(
                    model=settings.LLM_MAIN_MODEL,
                    api_key=settings.ANTHROPIC_API_KEY,
                    max_tokens=settings.LLM_MAX_TOKENS,
                ),
                # Fallback
                ChatGoogleGenerativeAI(
                    model=settings.LLM_CHEAP_MODEL,
                    google_api_key=settings.GOOGLE_API_KEY,
                ),
            ],
            "hard": [
                ChatAnthropic(
                    model=settings.LLM_HARD_MODEL,
                    api_key=settings.ANTHROPIC_API_KEY,
                    max_tokens=settings.LLM_MAX_TOKENS,
                ),
                ChatOpenAI(
                    model="gpt-4o",
                    api_key=settings.OPENAI_API_KEY,
                ),
            ],
        }

    def get_model(self, tier: Tier = "main") -> BaseChatModel:
        """Return primary model for tier."""
        return self._models[tier][0]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def invoke(
        self,
        messages: list[BaseMessage],
        tier: Tier = "main",
    ) -> BaseMessage:
        """Invoke with retry. Falls back to next model in tier on hard failure."""
        models = self._models[tier]
        last_error: Exception | None = None

        for model in models:
            try:
                response = await model.ainvoke(messages)
                return response
            except Exception as e:
                logger.warning("llm_invoke_failed", model=type(model).__name__, error=str(e))
                last_error = e
                continue

        raise LLMError(f"All models in tier '{tier}' failed: {last_error}")

    async def stream(
        self,
        messages: list[BaseMessage],
        tier: Tier = "main",
    ) -> AsyncIterator[str]:
        """Stream tokens. No fallback during stream (would break UX)."""
        model = self.get_model(tier)
        async for chunk in model.astream(messages):
            if chunk.content:
                yield str(chunk.content)


llm_gateway = LLMGateway()
