from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.integrations.ai.registry import TIER_CHAT_ACCESS


try:
    JORDAN_TZ = ZoneInfo("Asia/Amman")
except ZoneInfoNotFoundError:
    JORDAN_TZ = timezone(timedelta(hours=3), name="Asia/Amman")


@dataclass(frozen=True)
class TierLimits:
    allowed_models: dict[str, set[str]]
    max_tokens: int
    max_messages_per_month: int
    max_docs_per_month: int
    max_extractions_per_month: int
    max_advisor_runs_per_month: int
    max_voice_clips_per_month: int


TIER_ORDER = ("Basic", "Pro", "Premium")

TIER_LIMITS: dict[str, TierLimits] = {
    "Basic": TierLimits(
        allowed_models={provider: set(models) for provider, models in TIER_CHAT_ACCESS["Basic"].items()},
        max_tokens=1024,
        max_messages_per_month=60,
        max_docs_per_month=10,
        max_extractions_per_month=10,
        max_advisor_runs_per_month=5,
        max_voice_clips_per_month=20,
    ),
    "Pro": TierLimits(
        allowed_models={provider: set(models) for provider, models in TIER_CHAT_ACCESS["Pro"].items()},
        max_tokens=2048,
        max_messages_per_month=200,
        max_docs_per_month=50,
        max_extractions_per_month=50,
        max_advisor_runs_per_month=25,
        max_voice_clips_per_month=80,
    ),
    "Premium": TierLimits(
        allowed_models={provider: set(models) for provider, models in TIER_CHAT_ACCESS["Premium"].items()},
        max_tokens=4096,
        max_messages_per_month=500,
        max_docs_per_month=150,
        max_extractions_per_month=150,
        max_advisor_runs_per_month=60,
        max_voice_clips_per_month=200,
    ),
}

TIER_DEFAULT_MODELS: dict[str, tuple[str, str]] = {
    "Basic": ("gemini", "gemini-2.5-flash"),
    "Pro": ("gemini", "gemini-2.5-flash"),
    "Premium": ("gemini", "gemini-2.5-flash"),
}


def normalize_tier(tier: str | None) -> str:
    if tier in TIER_LIMITS:
        return tier
    return "Basic"


def get_tier_limits(tier: str | None) -> TierLimits:
    return TIER_LIMITS[normalize_tier(tier)]


def operation_limit(tier: str | None, operation: str) -> int:
    limits = get_tier_limits(tier)
    return {
        "chat": limits.max_messages_per_month,
        "document_upload": limits.max_docs_per_month,
        "extraction": limits.max_extractions_per_month,
        "advisor": limits.max_advisor_runs_per_month,
        "voice": limits.max_voice_clips_per_month,
        "memory": limits.max_messages_per_month,
    }[operation]


def default_model_for_tier(tier: str | None) -> tuple[str, str]:
    return TIER_DEFAULT_MODELS[normalize_tier(tier)]


def tier_rank(tier: str | None) -> int:
    return TIER_ORDER.index(normalize_tier(tier))


def is_model_allowed(tier: str | None, provider: str, model: str) -> bool:
    limits = get_tier_limits(tier)
    return model in limits.allowed_models.get(provider, set())


def allowed_models_payload(tier: str | None) -> list[dict[str, str]]:
    limits = get_tier_limits(tier)
    return [
        {"provider": provider, "model": model}
        for provider, models in limits.allowed_models.items()
        for model in sorted(models)
    ]


def current_usage_month(now: datetime | None = None) -> date:
    local_now = (now or datetime.now(JORDAN_TZ)).astimezone(JORDAN_TZ)
    return date(local_now.year, local_now.month, 1)
