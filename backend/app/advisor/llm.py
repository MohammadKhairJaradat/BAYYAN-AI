"""Thin LLM client for the advisor pipeline.

Reads provider + model from settings. Supports anthropic, openai, gemini, groq.
Each provider has a per-call key check so a missing key produces a clean error.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable, Literal

from app.config import settings

logger = logging.getLogger(__name__)


async def complete(
    system: str,
    user: str,
    *,
    response_format: Literal["text", "json"] = "text",
    max_tokens: int | None = None,
) -> str:
    """Run a single-turn LLM completion. Returns the assistant text verbatim.

    JSON mode appends a strict instruction to the system prompt; the caller is
    responsible for parsing.
    """
    provider = settings.ADVISOR_LLM_PROVIDER.lower()
    model = settings.ADVISOR_LLM_MODEL
    max_tok = max_tokens or settings.ADVISOR_LLM_MAX_TOKENS

    if response_format == "json":
        system = system + "\n\nReturn strictly valid JSON. No prose, no markdown fences."

    fn = _DISPATCH.get(provider)
    if fn is None:
        raise RuntimeError(
            f"ADVISOR_LLM_PROVIDER={provider!r} is unknown. "
            "Supported: anthropic | openai | gemini | groq"
        )
    if provider == "gemini":
        return await asyncio.to_thread(fn, system, user, model, max_tok, response_format == "json")
    return await asyncio.to_thread(fn, system, user, model, max_tok)


async def complete_json(system: str, user: str, **kw: Any) -> dict[str, Any]:
    """Like complete(response_format='json') but parses and falls back gracefully."""
    raw = await complete(system, user, response_format="json", **kw)
    return _parse_json_safely(raw)


def _call_anthropic(system: str, user: str, model: str, max_tokens: int) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("anthropic", model=model, system=system, user=user, max_tokens=max_tokens)


def _call_openai(system: str, user: str, model: str, max_tokens: int) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("openai", model=model, system=system, user=user, max_tokens=max_tokens)


def _call_groq(system: str, user: str, model: str, max_tokens: int) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("groq", model=model, system=system, user=user, max_tokens=max_tokens)


def _call_gemini(system: str, user: str, model: str, max_tokens: int, json_mode: bool = False) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text("gemini", model=model, system=system, user=user, max_tokens=max_tokens, json_mode=json_mode)


_DISPATCH: dict[str, Callable[[str, str, str, int], str]] = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
    "gemini": _call_gemini,
    "groq": _call_groq,
}


def _parse_json_safely(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            logger.warning("advisor LLM returned non-JSON: no JSON object found")
            return {"error": "parse_failed", "raw": raw}
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            logger.warning("advisor LLM returned non-JSON: %s", exc)
            return {"error": "parse_failed", "raw": raw}

    if not isinstance(data, dict):
        logger.warning("advisor LLM returned JSON %s, expected object", type(data).__name__)
        return {"error": "parse_failed", "raw": raw}
    if data.get("error") == "parse_failed":
        return {"error": "parse_failed", "raw": raw}
    return data
