"""One bounded text-completion boundary for provider-backed features."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.integrations.ai.google import generate as google_generate
from app.integrations.ai.registry import SUPPORTED_PROVIDERS

PROVIDER_TIMEOUT_SECONDS = 30


@dataclass
class AIProviderError(RuntimeError):
    provider: str
    kind: str
    status_code: int | None = None

    def __str__(self) -> str:
        return f"{self.provider} {self.kind}"


def _provider_error(provider: str, exc: Exception) -> AIProviderError:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    status = status if isinstance(status, int) else None
    name = type(exc).__name__.lower()
    if status == 429 or "ratelimit" in name or "resourceexhausted" in name:
        kind = "rate_limit"
    elif "timeout" in name or "timed out" in str(exc).lower():
        kind = "timeout"
    elif status in {400, 422}:
        kind = "bad_request"
    else:
        kind = "unavailable"
    return AIProviderError(provider, kind, status)


def complete_text(
    provider: str,
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    json_mode: bool = False,
) -> str:
    """A single provider attempt with one timeout and no SDK retry loop."""
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")

    if provider == "anthropic":
        key = settings.ANTHROPIC_API_KEY
    elif provider == "openai":
        key = settings.OPENAI_API_KEY
    elif provider == "groq":
        key = settings.GROQ_API_KEY
    else:
        key = settings.GEMINI_API_KEY or settings.GOOGLE_AI_API_KEY
    if not key:
        raise AIProviderError(provider, "not_configured")

    try:
        if provider == "gemini":
            result = google_generate(
                api_key=key, model=model, prompt=user,
                system_instruction=system, max_output_tokens=max_tokens,
                response_mime_type="application/json" if json_mode else None,
            )
        elif provider == "anthropic":
            import anthropic

            with anthropic.Anthropic(
                api_key=key, timeout=PROVIDER_TIMEOUT_SECONDS, max_retries=0,
            ) as client:
                response = client.messages.create(
                    model=model, max_tokens=max_tokens, system=system,
                    messages=[{"role": "user", "content": user}],
                )
            result = response.content[0].text
        else:
            from openai import OpenAI

            kwargs = {"base_url": "https://api.groq.com/openai/v1"} if provider == "groq" else {}
            with OpenAI(
                api_key=key, timeout=PROVIDER_TIMEOUT_SECONDS, max_retries=0, **kwargs,
            ) as client:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **({"max_tokens": max_tokens} if provider == "groq" else {"max_completion_tokens": max_tokens}),
                )
            result = response.choices[0].message.content
    except AIProviderError:
        raise
    except Exception as exc:
        raise _provider_error(provider, exc) from exc
    if not isinstance(result, str) or not result.strip():
        raise AIProviderError(provider, "malformed_response")
    return result
