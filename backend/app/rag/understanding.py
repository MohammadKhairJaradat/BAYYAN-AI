"""LLM understanding layer for the chat router.

A single fast LLM call reads the *whole* conversation plus a compact snapshot of
the signed-in user's stored account and returns:

  - ``intent``  — which route the turn belongs to (same enum as ``qa.classify_chat_intent``)
  - ``stated``  — the tax/account slots the user has asserted across the conversation
                  (latest turn wins), so prior-turn figures survive into follow-ups
  - ``reasoning`` — short, for logging/debug

Contradiction detection (stated vs. stored) is done deterministically in Python
from ``stated`` + the snapshot — see ``account_context.build_profile_updates`` —
rather than trusting the model to echo stored values back.

Design:
  * **Hybrid** — obvious cases (bare greetings) short-circuit without an LLM call.
  * **Graceful fallback** — if the LLM call fails or returns invalid JSON, the
    caller falls back to the legacy regex router (``qa._intent_with_memory``) so
    chat never hard-fails. ``understand`` signals this by returning ``source``.

Tax math is NEVER done here — the model only understands and routes. The
deterministic ``tax_engine`` still computes every number.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .prompts_understanding import UNDERSTANDING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_VALID_INTENTS = {
    "direct_chat",
    "tax_general",
    "tax_legal_grounded",
    "tax_calculation",
    "off_topic",
}

# Allowed deduction categories the model may emit (mirror DeductionCategory values).
_VALID_DEDUCTION_CATEGORIES = {
    "medical",
    "education",
    "rent",
    "housing_interest",
    "housing_murabaha",
    "donations",
    "insurance",
    "pension",
}

# Internal router models per provider. Kept separate from the user-facing chat
# whitelist (qa._SUPPORTED_CHAT_MODELS): this is a cheap/fast internal classifier,
# not a model the user selected. A wrong id here is non-fatal — the caller falls
# back to the regex router.
_ROUTER_MODELS = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.1-8b-instant",
}

_ROUTER_MAX_TOKENS = 600


@dataclass(slots=True)
class Understanding:
    intent: str
    stated: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    source: str = "llm"  # "llm" | "fast_path" | "fallback"


def router_model_for(provider: str) -> str:
    return _ROUTER_MODELS.get(provider, _ROUTER_MODELS["anthropic"])


def _is_trivial_greeting(question: str) -> bool:
    """Fast-path: extremely short greeting/thanks with no tax content.

    Kept deliberately narrow so anything remotely ambiguous still reaches the LLM.
    """
    text = (question or "").strip()
    if not text or len(text) > 40:
        return False
    # Import lazily to avoid import cost / cycles at module load.
    from .qa import _DIRECT_CHAT_RE, _TAX_TOPIC_RE

    if _TAX_TOPIC_RE.search(text):
        return False
    return bool(_DIRECT_CHAT_RE.search(text))


def _coerce_stated(raw: Any) -> dict[str, Any]:
    """Validate/normalize the model's ``stated`` object into safe Python values."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out

    def _num(value: Any) -> float | None:
        try:
            if value is None or isinstance(value, bool):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int(value: Any) -> int | None:
        n = _num(value)
        return int(n) if n is not None else None

    gross = _num(raw.get("gross_income"))
    if gross is not None and gross >= 0:
        out["gross_income"] = gross

    marital = raw.get("marital_status")
    if isinstance(marital, str) and marital.strip().lower() in {"single", "married"}:
        out["marital_status"] = marital.strip().lower()

    deps = _int(raw.get("num_dependents"))
    if deps is not None and deps >= 0:
        out["num_dependents"] = deps

    withheld = _num(raw.get("tax_withheld"))
    if withheld is not None and withheld >= 0:
        out["tax_withheld"] = withheld

    for flag in ("claims_dependents_exemption", "claim_spouse_expense_exemption"):
        if isinstance(raw.get(flag), bool):
            out[flag] = raw[flag]

    disability = _int(raw.get("disability_exemption_count"))
    if disability is not None and disability >= 0:
        out["disability_exemption_count"] = disability

    employer = raw.get("employer_name")
    if isinstance(employer, str) and employer.strip():
        out["employer_name"] = employer.strip()[:120]

    deductions = raw.get("deductions")
    if isinstance(deductions, list):
        clean: list[dict[str, Any]] = []
        for item in deductions:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category", "")).strip().lower()
            amount = _num(item.get("amount"))
            if category in _VALID_DEDUCTION_CATEGORIES and amount is not None and amount >= 0:
                clean.append({"category": category, "amount": amount})
        if clean:
            out["deductions"] = clean

    return out


def _parse_understanding(text: str) -> Understanding | None:
    """Parse the model's JSON reply. Returns None on any malformed output."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip ```json fences if present.
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    intent = str(data.get("intent", "")).strip().lower()
    if intent not in _VALID_INTENTS:
        return None

    return Understanding(
        intent=intent,
        stated=_coerce_stated(data.get("stated")),
        reasoning=str(data.get("reasoning", ""))[:400],
        source="llm",
    )


def _build_user_message(
    question: str,
    conversation_context: Optional[str],
    snapshot: Optional[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if snapshot is not None:
        parts.append(
            "STORED_ACCOUNT (the signed-in user's saved profile; compare against what "
            "they state in chat):\n"
            + json.dumps(snapshot, ensure_ascii=False, default=str)
        )
    else:
        parts.append("STORED_ACCOUNT: none (no tax profile on file).")
    if conversation_context:
        parts.append("CONVERSATION_SO_FAR:\n" + conversation_context.strip())
    parts.append("CURRENT_USER_MESSAGE:\n" + (question or "").strip())
    return "\n\n".join(parts)


def understand(
    question: str,
    conversation_context: Optional[str] = None,
    snapshot: Optional[dict[str, Any]] = None,
    *,
    provider: str,
    model: Optional[str] = None,
) -> Understanding | None:
    """Return an Understanding, or None if the caller should use the regex fallback.

    ``provider`` is the resolved chat provider (anthropic|openai|gemini|groq).
    ``model`` overrides the internal router model (defaults to a fast model).
    """
    # Hybrid fast-path: skip the LLM for trivial greetings.
    if _is_trivial_greeting(question):
        return Understanding(intent="direct_chat", stated={}, source="fast_path")

    from .qa import _call_llm  # lazy import to avoid a circular import at load time

    router_model = (model or router_model_for(provider)).strip()
    user_message = _build_user_message(question, conversation_context, snapshot)

    try:
        reply = _call_llm(
            provider,
            user_message,
            router_model,
            system_prompt=UNDERSTANDING_SYSTEM_PROMPT,
            max_tokens=_ROUTER_MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001 — any provider error → regex fallback
        logger.warning("understanding LLM call failed (%s) — regex fallback", exc)
        return None

    parsed = _parse_understanding(reply or "")
    if parsed is None:
        logger.warning("understanding returned unparseable output — regex fallback")
        return None
    return parsed
