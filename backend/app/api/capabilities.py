"""Public, key-free product limits used by the plan comparison UI."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.tier_limits import TIER_LIMITS, TIER_ORDER, allowed_models_payload
from app.config import settings
from app.integrations.ai.registry import SUPPORTED_PROVIDERS, provider_is_configured

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


class AllowedModel(BaseModel):
    provider: str
    model: str


class TierCapability(BaseModel):
    name: str
    max_messages_per_month: int
    max_docs_per_month: int
    max_tokens: int
    max_extractions_per_month: int
    max_advisor_runs_per_month: int
    max_voice_clips_per_month: int
    allowed_models: list[AllowedModel]


class CapabilitiesResponse(BaseModel):
    product: Literal["BAYYAN"] = "BAYYAN"
    tier_changes: Literal["admin_only"] = "admin_only"
    official_filing: bool = False
    legal_corpus: Literal["demo"] = "demo"
    ai: "AIAvailability"
    tiers: list[TierCapability]


class AIAvailability(BaseModel):
    configured_providers: list[str]
    document_extraction: bool
    advisor: bool
    voice: bool


@router.get("", response_model=CapabilitiesResponse)
def get_capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        ai=AIAvailability(
            configured_providers=sorted(provider for provider in SUPPORTED_PROVIDERS if provider_is_configured(provider)),
            document_extraction=provider_is_configured("gemini") or provider_is_configured("anthropic"),
            advisor=provider_is_configured(settings.ADVISOR_LLM_PROVIDER.strip().lower()),
            voice=provider_is_configured("gemini"),
        ),
        tiers=[
            TierCapability(
                name=tier,
                max_messages_per_month=TIER_LIMITS[tier].max_messages_per_month,
                max_docs_per_month=TIER_LIMITS[tier].max_docs_per_month,
                max_tokens=TIER_LIMITS[tier].max_tokens,
                max_extractions_per_month=TIER_LIMITS[tier].max_extractions_per_month,
                max_advisor_runs_per_month=TIER_LIMITS[tier].max_advisor_runs_per_month,
                max_voice_clips_per_month=TIER_LIMITS[tier].max_voice_clips_per_month,
                allowed_models=allowed_models_payload(tier),
            )
            for tier in TIER_ORDER
        ]
    )
