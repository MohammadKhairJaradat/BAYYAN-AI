"""Session-scoped chat memory helpers.

Raw messages remain the durable transcript. This module maintains a compact
summary on chat_sessions and builds the small memory packet sent to qa.answer().
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.auth.tier_limits import normalize_tier
from app.auth.usage import reserve_usage, settle_usage
from app.models.connection import async_session_factory
from app.models.database import ChatMessage, ChatSession, User
from app.rag.prompts import MEMORY_SUMMARY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

RECENT_MESSAGE_LIMIT = 8
CONVERSATION_CONTEXT_CHAR_LIMIT = 6000
MESSAGE_CONTEXT_CHAR_LIMIT = 1200
MEMORY_SUMMARY_CHAR_LIMIT = 3000
MEMORY_MAX_TOKENS = 512
GEMINI_MEMORY_MODEL = "gemini-2.5-flash"
STALE_REFRESH_RETRY_LIMIT = 1


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n[truncated]"


def _format_message(message: ChatMessage) -> str:
    role = (message.role or "message").strip().lower()
    kind = (message.kind or "text").strip().lower()
    prefix = role.capitalize()
    if kind != "text":
        prefix = f"{prefix} ({kind})"
    return f"{prefix}: {_clip((message.content or '').strip(), MESSAGE_CONTEXT_CHAR_LIMIT)}"


def _format_messages(messages: Sequence[ChatMessage]) -> str:
    return "\n".join(
        line for message in messages if (line := _format_message(message).strip())
    )


async def _recent_messages(
    db: AsyncSession,
    session_id: uuid.UUID,
    *,
    limit: int = RECENT_MESSAGE_LIMIT,
) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


async def build_conversation_context(
    db: AsyncSession,
    session: ChatSession,
    *,
    recent_limit: int = RECENT_MESSAGE_LIMIT,
) -> str | None:
    """Build the memory packet sent with the next user question."""

    parts: list[str] = []
    summary = (session.memory_summary or "").strip()
    if summary:
        parts.append(f"Session memory summary:\n{_clip(summary, MEMORY_SUMMARY_CHAR_LIMIT)}")

    recent = await _recent_messages(db, session.id, limit=recent_limit)
    recent_text = _format_messages(recent)
    if recent_text:
        parts.append(f"Recent prior messages:\n{recent_text}")

    context = "\n\n".join(parts).strip()
    if not context:
        return None
    return _clip(context, CONVERSATION_CONTEXT_CHAR_LIMIT)


async def build_conversation_context_for_session(
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
) -> str | None:
    if session_id is None:
        return None

    try:
        async with async_session_factory() as db:
            session = await db.get(ChatSession, session_id)
            if session is None or session.user_id != user_id:
                return None
            return await build_conversation_context(db, session)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to build chat memory context for %s: %s", session_id, exc)
        return None


def _memory_prompt(
    previous_summary: str | None,
    messages: Sequence[ChatMessage],
    lang: str = "ar",
) -> str:
    summary = (previous_summary or "").strip() or "(none yet)"
    turns = _format_messages(messages) or "(no new messages)"
    return (
        f"Language hint: {lang or 'ar'}\n\n"
        f"Previous summary:\n{summary}\n\n"
        f"New transcript turns to merge:\n{turns}\n\n"
        "Return the updated compact memory only."
    )


def _call_gemini_memory(user_prompt: str) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "gemini", model=GEMINI_MEMORY_MODEL, system=MEMORY_SUMMARY_SYSTEM_PROMPT,
        user=user_prompt, max_tokens=MEMORY_MAX_TOKENS,
    )


def _call_openai_memory(user_prompt: str, provider: str) -> str:
    from app.integrations.ai.adapters import complete_text
    if provider not in {"groq", "openai"}:
        raise ValueError(f"Unsupported memory provider: {provider}")
    return complete_text(
        provider,
        model=settings.GROQ_CHAT_MODEL if provider == "groq" else settings.OPENAI_CHAT_MODEL,
        system=MEMORY_SUMMARY_SYSTEM_PROMPT,
        user=user_prompt, max_tokens=MEMORY_MAX_TOKENS,
    )


def _call_anthropic_memory(user_prompt: str) -> str:
    from app.integrations.ai.adapters import complete_text
    return complete_text(
        "anthropic", model=settings.ANTHROPIC_CHAT_MODEL,
        system=MEMORY_SUMMARY_SYSTEM_PROMPT,
        user=user_prompt, max_tokens=MEMORY_MAX_TOKENS,
    )


def _provider_candidates(preferred_provider: str | None) -> list[str]:
    candidates = ["gemini"]
    for provider in [preferred_provider, settings.LLM_PROVIDER]:
        normalized = (provider or "").strip().lower()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    # At most two providers per summary and one stale-write retry: four
    # provider attempts at most for one reserved memory operation.
    return candidates[:2]


def generate_memory_summary(
    previous_summary: str | None,
    messages: Sequence[ChatMessage],
    *,
    lang: str = "ar",
    preferred_provider: str | None = None,
) -> str:
    """Generate an updated compact memory summary.

    Gemini Flash is tried first. If it is unavailable, the selected/current
    chat provider is tried as a fallback.
    """

    user_prompt = _memory_prompt(previous_summary, messages, lang)
    errors: list[str] = []

    for provider in _provider_candidates(preferred_provider):
        try:
            if provider == "gemini":
                raw = _call_gemini_memory(user_prompt)
            elif provider in {"openai", "groq"}:
                raw = _call_openai_memory(user_prompt, provider)
            elif provider == "anthropic":
                raw = _call_anthropic_memory(user_prompt)
            else:
                continue
            summary = _clip((raw or "").strip(), MEMORY_SUMMARY_CHAR_LIMIT)
            if summary:
                return summary
            errors.append(f"{provider}: empty response")
        except Exception as exc:  # noqa: BLE001
            logger.warning("chat memory summary via %s failed: %s", provider, exc)
            errors.append(f"{provider}: {exc}")

    raise RuntimeError("No chat memory summarizer succeeded: " + "; ".join(errors))


async def persist_memory_summary_if_fresh(
    session_id: uuid.UUID,
    expected_message_count: int,
    new_summary: str,
    new_message_count: int,
) -> bool:
    async with async_session_factory() as db:
        result = await db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .where(ChatSession.memory_message_count == expected_message_count)
            .values(
                memory_summary=new_summary,
                memory_message_count=new_message_count,
                memory_updated_at=func.now(),
            )
        )
        await db.commit()
        return bool(result.rowcount)


async def refresh_session_memory(
    session_id: uuid.UUID,
    *,
    lang: str = "ar",
    preferred_provider: str | None = None,
) -> None:
    """Best-effort background task that merges new transcript turns into memory."""
    reservation_id: uuid.UUID | None = None
    try:
        for attempt in range(STALE_REFRESH_RETRY_LIMIT + 1):
            async with async_session_factory() as db:
                session = await db.get(ChatSession, session_id)
                if session is None:
                    return

                expected_count = session.memory_message_count or 0
                total_count = await db.scalar(
                    select(func.count())
                    .select_from(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                )
                total_count = int(total_count or 0)
                if total_count <= expected_count:
                    return

                result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at.asc())
                    .offset(expected_count)
                )
                new_messages = result.scalars().all()
                previous_summary = session.memory_summary

                if reservation_id is None:
                    user = await db.get(User, session.user_id)
                    if user is None:
                        return
                    reservation_id = await reserve_usage(
                        db, user_id=user.id,
                        tier=normalize_tier(user.subscription_tier),
                        operation="memory",
                        idempotency_key=f"{session_id}:{total_count}",
                    )

            new_summary = await asyncio.to_thread(
                generate_memory_summary,
                previous_summary,
                new_messages,
                lang=lang,
                preferred_provider=preferred_provider,
            )
            updated = await persist_memory_summary_if_fresh(
                session_id,
                expected_count,
                new_summary,
                total_count,
            )
            if updated:
                return

            if attempt < STALE_REFRESH_RETRY_LIMIT:
                logger.info(
                    "Retrying stale chat memory update for session %s "
                    "(attempt %s/%s)",
                    session_id,
                    attempt + 1,
                    STALE_REFRESH_RETRY_LIMIT,
                )

        logger.info("Skipped stale chat memory update for session %s", session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to refresh chat memory for %s: %s", session_id, exc)
    finally:
        if reservation_id is not None:
            async with async_session_factory() as db:
                await settle_usage(db, reservation_id)


def schedule_memory_refresh(
    session_id: uuid.UUID,
    *,
    lang: str = "ar",
    preferred_provider: str | None = None,
) -> None:
    async def _runner() -> None:
        await refresh_session_memory(
            session_id,
            lang=lang,
            preferred_provider=preferred_provider,
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("No running event loop for chat memory refresh: %s", session_id)
        return
    loop.create_task(_runner())
