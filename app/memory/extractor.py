"""Memory extractor — uses a cheap LLM to pull durable facts from chat turns.

Strategy:
  - After each assistant response, extract candidate memories.
  - Filter by type: factual / preference / context / episodic.
  - Skip if low-signal (greetings, small talk).
  - PII-redact before storage.

We don't use mem0 library directly here because we want full control over the
storage schema (tenant_id, ACL, audit). mem0's approach is borrowed but reimplemented.
"""
import json
from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.logging import get_logger
from app.services.llm_gateway import llm_gateway

logger = get_logger(__name__)


EXTRACT_SYSTEM = """You are a memory extraction system. Given a recent conversation turn, extract durable facts about the user that would be useful to remember for future conversations.

Output ONLY valid JSON:
{
  "memories": [
    {"type": "factual|preference|context|episodic", "content": "<concise statement>"},
    ...
  ]
}

Rules:
- factual: long-term truths about the user (job, location, name, family)
- preference: how they like to communicate or be helped (language, tone, format)
- context: current ongoing situation (project, goal) — may expire
- episodic: a specific event mentioned (resolves in 90d)
- Skip greetings, small talk, one-off questions.
- Skip anything containing emails, phone numbers, or government IDs — those are PII.
- Maximum 5 memories per turn. Empty array if nothing to remember.
- Write in the same language as the user."""


@dataclass
class ExtractedMemory:
    memory_type: str
    content: str


async def extract_memories(
    user_message: str,
    assistant_message: str,
) -> list[ExtractedMemory]:
    """Run extraction on the latest turn. Returns 0–5 candidates."""
    if not user_message.strip():
        return []

    conversation = f"User: {user_message}\nAssistant: {assistant_message}"

    try:
        response = await llm_gateway.invoke(
            [
                SystemMessage(content=EXTRACT_SYSTEM),
                HumanMessage(content=conversation),
            ],
            tier="cheap",
        )
        content = str(response.content).strip()
        # Strip markdown fences
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        raw_memories = data.get("memories", [])

        valid_types = {"factual", "preference", "context", "episodic"}
        result: list[ExtractedMemory] = []
        for m in raw_memories[:5]:
            if not isinstance(m, dict):
                continue
            mtype = m.get("type", "").lower()
            mcontent = m.get("content", "").strip()
            if mtype not in valid_types or not mcontent:
                continue
            result.append(ExtractedMemory(memory_type=mtype, content=mcontent))

        logger.info("memories_extracted", count=len(result))
        return result
    except Exception as e:
        logger.warning("memory_extract_failed", error=str(e))
        return []
