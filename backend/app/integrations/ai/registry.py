"""Single backend source for selectable chat models and tier access."""

from __future__ import annotations

from app.config import settings

SUPPORTED_CHAT_MODELS: dict[str, frozenset[str]] = {
    "gemini": frozenset({"gemini-2.5-flash", "gemini-2.5-pro"}),
    "openai": frozenset({"gpt-5.4", "gpt-4o"}),
    "anthropic": frozenset({"claude-opus-4-7"}),
    "groq": frozenset({"llama-3.1-8b-instant"}),
}
SUPPORTED_PROVIDERS = frozenset(SUPPORTED_CHAT_MODELS)


def provider_is_configured(provider: str) -> bool:
    """Report readiness without exposing or testing a credential."""
    return bool({
        "gemini": settings.GEMINI_API_KEY or settings.GOOGLE_AI_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
        "groq": settings.GROQ_API_KEY,
    }.get(provider))

TIER_CHAT_ACCESS: dict[str, dict[str, frozenset[str]]] = {
    "Basic": {
        "groq": frozenset({"llama-3.1-8b-instant"}),
        "gemini": frozenset({"gemini-2.5-flash"}),
    },
    "Pro": {
        "groq": frozenset({"llama-3.1-8b-instant"}),
        "gemini": frozenset({"gemini-2.5-flash"}),
        "openai": frozenset({"gpt-4o"}),
    },
    "Premium": {
        "groq": frozenset({"llama-3.1-8b-instant"}),
        "gemini": frozenset({"gemini-2.5-flash", "gemini-2.5-pro"}),
        "openai": frozenset({"gpt-4o", "gpt-5.4"}),
        "anthropic": frozenset({"claude-opus-4-7"}),
    },
}

for tier, access in TIER_CHAT_ACCESS.items():
    for provider, models in access.items():
        if not models <= SUPPORTED_CHAT_MODELS[provider]:
            raise RuntimeError(f"{tier} access contains an unregistered {provider} model")
