import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_active_user
from app.models.connection import async_session_factory, get_db
from app.models.database import ChatMessage, ChatSession, User
from app.models.schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ChatSessionCreate,
    ChatSessionRead,
    ChatSessionUpdate,
    ChatSessionWithMessages,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat/sessions", tags=["chat-history"])

_VALID_ROLES = {"user"}
_VALID_KINDS = {"text", "voice", "upload"}


async def _get_owned_session(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    with_messages: bool = False,
) -> ChatSession:
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    if with_messages:
        stmt = stmt.options(selectinload(ChatSession.messages))
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None or session.user_id != user_id:
        # Same 404 either way — no enumeration leak.
        raise HTTPException(status_code=404, detail="Chat session not found")
    return session


@router.post(
    "",
    response_model=ChatSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: ChatSessionCreate | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    title = (payload.title if payload and payload.title else "New chat").strip() or "New chat"
    session = ChatSession(user_id=current_user.id, title=title[:120])
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[ChatSessionRead])
async def list_sessions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/{session_id}", response_model=ChatSessionWithMessages)
async def get_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_session(
        session_id, current_user.id, db, with_messages=True
    )


@router.patch("/{session_id}", response_model=ChatSessionRead)
async def rename_session(
    session_id: uuid.UUID,
    payload: ChatSessionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    session = await _get_owned_session(session_id, current_user.id, db)
    session.title = title[:120]
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    await db.delete(session)
    await db.commit()
    return None


@router.post(
    "/{session_id}/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def log_message(
    session_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {payload.role!r}. Allowed: {sorted(_VALID_ROLES)}",
        )
    if payload.kind not in _VALID_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid kind: {payload.kind!r}. Allowed: {sorted(_VALID_KINDS)}",
        )

    session = await _get_owned_session(session_id, current_user.id, db)
    message = ChatMessage(
        session_id=session.id,
        role=payload.role,
        kind=payload.kind,
        content=payload.content,
    )
    db.add(message)
    # Bump updated_at so the sidebar re-orders.
    session.updated_at = func.now()
    await db.commit()
    await db.refresh(message)
    return message


async def generate_and_save_title(
    session_id: uuid.UUID,
    question: str,
    answer: str,
    lang: str,
    provider: str | None,
) -> None:
    """Background task: derive title from the first 5 words of the user message."""
    title = " ".join((question or "").split()[:5]).strip()[:120]
    if not title:
        return

    try:
        async with async_session_factory() as db:
            session = await db.get(ChatSession, session_id)
            if session and session.title == "New chat":
                session.title = title
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to persist generated title for session %s: %s", session_id, exc
        )
