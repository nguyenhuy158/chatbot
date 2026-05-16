"""Onboarding endpoints — first-time user experience.

Returns localized welcome, sample prompts, capability tour. Frontend renders
these in the empty state of the chat UI.
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.core.deps import DbSession, User
from app.db.models import User as UserModel
from app.i18n import t
from app.tools import get_tools_for_role

router = APIRouter()


class SamplePrompt(BaseModel):
    label: str
    query: str
    category: str


class CapabilityTourStep(BaseModel):
    title: str
    description: str
    icon: str  # emoji or icon key


class OnboardingResponse(BaseModel):
    welcome: str
    ai_disclosure: str
    sample_prompts: list[SamplePrompt]
    capability_tour: list[CapabilityTourStep]
    lang: str
    user_name: str | None


@router.get("/onboarding", response_model=OnboardingResponse)
async def onboarding(
    user: User,
    db: DbSession,
    lang: str = Query("vi", pattern="^(vi|en)$"),
) -> OnboardingResponse:
    # Get name from DB
    result = await db.execute(select(UserModel).where(UserModel.id == user.user_id))
    user_record = result.scalar_one_or_none()
    name = user_record.name if user_record else None

    welcome = (
        t("welcome_with_name", lang=lang, name=name) if name else t("welcome", lang=lang)
    )

    # Build sample prompts — role-aware
    samples: list[SamplePrompt] = []
    samples.append(SamplePrompt(label="FAQ", query=t("sample_faq", lang=lang), category="faq"))
    samples.append(SamplePrompt(label="Docs", query=t("sample_doc", lang=lang), category="rag"))

    role_tools = {tool.name for tool in get_tools_for_role(user.role)}
    if "calculator" in role_tools:
        samples.append(
            SamplePrompt(label="Calculator", query=t("sample_calc", lang=lang), category="tool")
        )
    if "web_search" in role_tools:
        samples.append(
            SamplePrompt(label="News", query=t("sample_news", lang=lang), category="tool")
        )

    # Capability tour — 3-step modal for first visit
    if lang == "vi":
        tour = [
            CapabilityTourStep(
                title="Hỏi mọi câu",
                description="Tôi có thể trả lời câu hỏi về tài liệu nội bộ và kiến thức chung.",
                icon="💬",
            ),
            CapabilityTourStep(
                title="Tay chân thật",
                description="Tôi có thể search web, tính toán, đọc ảnh — không chỉ chat.",
                icon="🔧",
            ),
            CapabilityTourStep(
                title="Nhớ bạn",
                description="Tôi sẽ nhớ sở thích để trả lời ngày càng phù hợp. Bạn có thể xem/xóa memory bất cứ lúc nào.",
                icon="🧠",
            ),
        ]
    else:
        tour = [
            CapabilityTourStep(
                title="Ask anything",
                description="I can answer about internal docs and general knowledge.",
                icon="💬",
            ),
            CapabilityTourStep(
                title="Real capabilities",
                description="I can search the web, calculate, read images — not just chat.",
                icon="🔧",
            ),
            CapabilityTourStep(
                title="I remember you",
                description="I'll remember preferences to improve responses. You can view/delete memories anytime.",
                icon="🧠",
            ),
        ]

    return OnboardingResponse(
        welcome=welcome,
        ai_disclosure=t("ai_disclosure", lang=lang),
        sample_prompts=samples,
        capability_tour=tour,
        lang=lang,
        user_name=name,
    )
