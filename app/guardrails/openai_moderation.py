"""OpenAI Moderation API wrapper.

Free API, strong on English, weaker on Vietnamese. We pair it with VN regex.

Returns category flags (sexual, violence, harassment, hate, self-harm, etc.)
plus scores. We block on hard categories; warn on borderline.
"""
from dataclasses import dataclass

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ModerationResult:
    flagged: bool
    categories: dict[str, bool]
    scores: dict[str, float]


# Categories we hard-block on (any single one triggers block)
HARD_BLOCK_CATEGORIES = {
    "sexual/minors",
    "violence/graphic",
    "self-harm/instructions",
}

# Borderline — warn + log, don't block by default
BORDERLINE_CATEGORIES = {
    "harassment",
    "hate",
    "self-harm",
    "sexual",
    "violence",
}


class OpenAIModeration:
    def __init__(self):
        self._client: AsyncOpenAI | None = None

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def check(self, text: str) -> ModerationResult:
        """Run moderation. Empty/clean on error so we don't accidentally block legit traffic."""
        if not text.strip():
            return ModerationResult(flagged=False, categories={}, scores={})

        if not settings.OPENAI_API_KEY:
            # No key → skip silently. VN regex still runs.
            return ModerationResult(flagged=False, categories={}, scores={})

        try:
            response = await self.client.moderations.create(
                model="omni-moderation-latest",
                input=text,
            )
            result = response.results[0]
            return ModerationResult(
                flagged=result.flagged,
                categories={k: bool(v) for k, v in result.categories.model_dump().items()},
                scores={k: float(v) for k, v in result.category_scores.model_dump().items()},
            )
        except Exception as e:
            logger.warning("openai_moderation_failed", error=str(e))
            return ModerationResult(flagged=False, categories={}, scores={})

    def should_block(self, result: ModerationResult) -> tuple[bool, list[str]]:
        """Decide block vs allow. Returns (block, reasons)."""
        triggered = [cat for cat, flag in result.categories.items() if flag]
        hard_hits = [c for c in triggered if c in HARD_BLOCK_CATEGORIES]
        if hard_hits:
            return True, hard_hits
        # If flagged on borderline + score > 0.9, also block
        borderline_high = [
            c for c in triggered
            if c in BORDERLINE_CATEGORIES and result.scores.get(c, 0) > 0.9
        ]
        if borderline_high:
            return True, borderline_high
        return False, triggered


openai_moderation = OpenAIModeration()
