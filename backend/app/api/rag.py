import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat_sessions import generate_and_save_title
from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import (
    default_model_for_tier,
    get_tier_limits,
    is_model_allowed,
    normalize_tier,
)
from app.auth.usage import reserve_usage, settle_usage
from app.config import settings
from app.integrations.ai.registry import SUPPORTED_PROVIDERS as _SUPPORTED_PROVIDERS, provider_is_configured
from app.models.connection import get_db
from app.models.database import ChatMessage, ChatSession, User
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ChatSource,
    RAGChunk,
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.rag import retrieve_with_context
from app.rag.account_context import (
    build_account_chat_context,
    build_profile_updates,
    merge_tax_inputs,
)
from app.rag.memory import build_conversation_context, refresh_session_memory
from app.rag.qa import answer as qa_answer, resolve_chat_model
from app.rag.understanding import understand

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])

_LLM_FAILURE_MESSAGE = (
    "Sorry — I couldn't generate a reply right now. "
    "Try a different model, or make sure the API key for your "
    "selected provider is set in the backend .env."
)


def _combine_context(*parts: str | None) -> str | None:
    context_parts = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(context_parts) if context_parts else None


def _merge_sources(*groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[tuple[str | None, str | None, str | None]] = set()
    for group in groups:
        for source in group:
            key = (
                source.get("kind"),
                source.get("citation"),
                source.get("label"),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)
    return merged


@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(
    payload: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user),
):
    chunks, context = await asyncio.to_thread(
        retrieve_with_context,
        payload.question,
        payload.top_k,
        payload.source_type,
        payload.lang,
    )

    return RAGQueryResponse(
        chunks=[
            RAGChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                score=c.score,
                citation=c.citation,
                metadata=c.metadata,
            )
            for c in chunks
        ],
        context=context,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    background: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    provider = payload.provider.strip().lower() if payload.provider else None
    provider = provider or None
    requested_model = payload.model.strip() if payload.model else None
    tier = normalize_tier(current_user.subscription_tier)
    limits = get_tier_limits(tier)

    if requested_model and not provider:
        raise HTTPException(
            status_code=400,
            detail="provider is required when model is specified",
        )

    if provider:
        chosen_provider = provider
        if chosen_provider not in _SUPPORTED_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {chosen_provider!r}. "
                f"Supported: {sorted(_SUPPORTED_PROVIDERS)}",
            )
        try:
            chosen_model = resolve_chat_model(chosen_provider, requested_model)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        chosen_provider = settings.LLM_PROVIDER.strip().lower()
        try:
            chosen_model = resolve_chat_model(chosen_provider, None)
        except ValueError:
            chosen_provider, chosen_model = default_model_for_tier(tier)
        else:
            if not is_model_allowed(tier, chosen_provider, chosen_model):
                chosen_provider, chosen_model = default_model_for_tier(tier)

    if not is_model_allowed(tier, chosen_provider, chosen_model):
        raise HTTPException(
            status_code=403,
            detail=(
                f"{chosen_model} is not available on your {tier} plan. "
                "Upgrade your tier or choose an allowed model."
            ),
        )

    if not provider_is_configured(chosen_provider):
        raise HTTPException(
            status_code=503,
            detail=f"{chosen_provider} is not configured for chat. Choose an available provider or ask the local operator to configure its API key.",
        )

    # ── 1. Resolve / create session + user message; commit immediately ─────
    # Committing now means a sidebar entry survives an LLM failure.
    if payload.session_id is not None:
        session = await db.get(ChatSession, payload.session_id)
        if session is None or session.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Chat session not found")
        # "First turn" = no prior messages logged. The frontend pre-creates a
        # session before sending text (Chat.tsx handleSend), so we can't infer
        # first-turn from session_id presence — check the message table instead.
        prior = await db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session.id)
        )
        was_first_turn = (prior or 0) == 0
    else:
        session = ChatSession(user_id=current_user.id, title="New chat")
        db.add(session)
        await db.flush()
        was_first_turn = True

    conversation_context = await build_conversation_context(db, session)
    account_context = await build_account_chat_context(
        db,
        user_id=current_user.id,
        question=payload.question,
    )
    combined_context = _combine_context(account_context.context, conversation_context)

    reservation_id = await reserve_usage(
        db, user_id=current_user.id, tier=tier, operation="chat",
        idempotency_key=idempotency_key,
    )

    # ── Understanding layer: LLM route + slot merge (carry prior-turn figures) +
    # contradiction detection. Falls back to the regex router when it returns None.
    try:
        understanding = await asyncio.to_thread(
            understand,
            payload.question,
            conversation_context,
            account_context.snapshot,
            provider=chosen_provider,
        )
    finally:
        # Accepted chat attempts count even if provider work fails. Release is
        # reserved for validation/storage failures before a provider call.
        await settle_usage(db, reservation_id)
    if understanding is not None:
        intent_override = understanding.intent
        merged_inputs = merge_tax_inputs(account_context.base_inputs, understanding.stated)
        calc_inputs = (
            merged_inputs
            if (understanding.stated or account_context.base_inputs is not None)
            else None
        )
        profile_updates = build_profile_updates(
            understanding.stated,
            account_context.profile,
            account_context.income_sources,
            account_context.deductions,
        )
    else:
        intent_override = None
        calc_inputs = account_context.tax_inputs
        profile_updates = []

    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        kind="text",
        content=payload.question,
    )
    db.add(user_msg)
    await db.commit()
    await db.refresh(session)
    await db.refresh(user_msg)

    # ── 2. Call the LLM (best-effort) ──────────────────────────────────────
    try:
        result = await asyncio.to_thread(
            qa_answer,
            payload.question,
            top_k=5,
            source_type=None,
            lang=payload.lang,
            provider=chosen_provider,
            model=chosen_model,
            max_tokens=limits.max_tokens,
            conversation_context=combined_context,
            tax_inputs=calc_inputs,
            intent_override=intent_override,
        )
        answer_text: str = result["answer"]
        sources = _merge_sources(result.get("sources") or [], account_context.sources)
        tax_breakdown = result.get("tax_breakdown")
        provider_used: str = result.get("provider") or "unknown"
        model_used: str | None = result.get("model")
    except Exception:
        logger.exception("Chat LLM call failed for user %s", current_user.id)
        answer_text = _LLM_FAILURE_MESSAGE
        sources = []
        tax_breakdown = None
        provider_used = "error"
        model_used = None

    # ── 3. Save assistant message (real or error) and commit ───────────────
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        kind="text",
        content=answer_text,
        sources=sources,
        tax_breakdown=tax_breakdown,
        provider=provider_used,
        model=model_used,
    )
    db.add(assistant_msg)
    session.updated_at = func.now()
    await db.commit()
    await db.refresh(assistant_msg)

    # ── 4. Title from first 5 words of the user's first message ────────────
    if was_first_turn:
        background.add_task(
            generate_and_save_title,
            session_id=session.id,
            question=payload.question,
            answer=answer_text,
            lang=payload.lang,
            provider=chosen_provider,
        )
    background.add_task(
        refresh_session_memory,
        session_id=session.id,
        lang=payload.lang,
        preferred_provider=chosen_provider,
    )

    return ChatResponse(
        answer=answer_text,
        sources=[ChatSource(**s) for s in sources],
        provider=provider_used,
        model=model_used,
        tax_breakdown=tax_breakdown,
        profile_updates=profile_updates,
        profile_id=account_context.profile_id,
        session_id=session.id,
        user_message_id=user_msg.id,
        assistant_message_id=assistant_msg.id,
    )
