from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.database import ChatMessage, ChatSession, User
from app.rag import memory


async def _user(db_session, username: str = "memory@example.com") -> User:
    user = User(username=username, hashed_password="hashed", name="Memory User")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_build_conversation_context_uses_summary_and_recent_messages(
    db_session,
):
    user = await _user(db_session)
    session = ChatSession(
        user_id=user.id,
        title="Memory test",
        memory_summary="Known facts:\n- Annual salary: 20000 JOD.",
        memory_message_count=4,
    )
    db_session.add(session)
    await db_session.flush()

    base = datetime(2026, 5, 29, tzinfo=timezone.utc)
    for index in range(10):
        db_session.add(
            ChatMessage(
                session_id=session.id,
                role="user" if index % 2 == 0 else "assistant",
                kind="text",
                content=f"message {index}",
                created_at=base + timedelta(seconds=index),
            )
        )
    await db_session.commit()
    await db_session.refresh(session)

    context = await memory.build_conversation_context(db_session, session)

    assert context is not None
    assert "Annual salary: 20000 JOD" in context
    assert "message 9" in context
    assert "message 2" in context
    assert "message 1" not in context


def test_generate_memory_summary_falls_back_from_gemini(monkeypatch):
    def fail_gemini(_prompt):
        raise RuntimeError("no gemini")

    def fallback_openai(_prompt, provider):
        assert provider == "openai"
        return "Known facts:\n- Salary: 20000 JOD."

    monkeypatch.setattr(memory, "_call_gemini_memory", fail_gemini)
    monkeypatch.setattr(memory, "_call_openai_memory", fallback_openai)

    result = memory.generate_memory_summary(
        None,
        [],
        lang="en",
        preferred_provider="openai",
    )

    assert "Salary: 20000 JOD" in result


@pytest.mark.asyncio
async def test_refresh_session_memory_updates_compact_summary(
    db_session,
    monkeypatch,
):
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(memory, "async_session_factory", TestSessionFactory)
    monkeypatch.setattr(
        memory,
        "generate_memory_summary",
        lambda *_args, **_kwargs: "Known facts:\n- Salary: 20000 JOD.",
    )

    user = await _user(db_session, "refresh@example.com")
    session = ChatSession(user_id=user.id, title="Refresh")
    db_session.add(session)
    await db_session.flush()
    db_session.add_all(
        [
            ChatMessage(session_id=session.id, role="user", kind="text", content="Salary 20000 JOD"),
            ChatMessage(session_id=session.id, role="assistant", kind="text", content="Noted."),
        ]
    )
    await db_session.commit()

    await memory.refresh_session_memory(session.id, lang="en", preferred_provider="gemini")
    await db_session.refresh(session)

    assert "Salary: 20000 JOD" in (session.memory_summary or "")
    assert session.memory_message_count == 2
    assert session.memory_updated_at is not None


@pytest.mark.asyncio
async def test_refresh_session_memory_keeps_old_state_when_summarizer_fails(
    db_session,
    monkeypatch,
):
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(memory, "async_session_factory", TestSessionFactory)

    def fail_summary(*_args, **_kwargs):
        raise RuntimeError("summary failed")

    monkeypatch.setattr(memory, "generate_memory_summary", fail_summary)

    user = await _user(db_session, "failure@example.com")
    session = ChatSession(user_id=user.id, title="Failure")
    db_session.add(session)
    await db_session.flush()
    db_session.add(
        ChatMessage(session_id=session.id, role="user", kind="text", content="Salary 20000")
    )
    await db_session.commit()

    await memory.refresh_session_memory(session.id, lang="en", preferred_provider="gemini")
    await db_session.refresh(session)

    assert session.memory_summary is None
    assert session.memory_message_count == 0


@pytest.mark.asyncio
async def test_persist_memory_summary_rejects_stale_background_update(
    db_session,
    monkeypatch,
):
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(memory, "async_session_factory", TestSessionFactory)

    user = await _user(db_session, "stale@example.com")
    session = ChatSession(
        user_id=user.id,
        title="Stale",
        memory_summary="Known facts:\n- Existing fact.",
        memory_message_count=1,
    )
    db_session.add(session)
    await db_session.commit()

    updated = await memory.persist_memory_summary_if_fresh(
        session.id,
        expected_message_count=0,
        new_summary="Overwritten by stale task",
        new_message_count=2,
    )
    await db_session.refresh(session)

    assert updated is False
    assert session.memory_summary == "Known facts:\n- Existing fact."
    assert session.memory_message_count == 1


@pytest.mark.asyncio
async def test_refresh_session_memory_retries_after_stale_update(
    db_session,
    monkeypatch,
):
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(memory, "async_session_factory", TestSessionFactory)

    user = await _user(db_session, "retry@example.com")
    session = ChatSession(user_id=user.id, title="Retry")
    db_session.add(session)
    await db_session.flush()
    db_session.add_all(
        [
            ChatMessage(session_id=session.id, role="user", kind="text", content="Salary 20000 JOD"),
            ChatMessage(session_id=session.id, role="assistant", kind="text", content="Noted."),
            ChatMessage(session_id=session.id, role="user", kind="text", content="What if married?"),
            ChatMessage(session_id=session.id, role="assistant", kind="text", content="Using salary 20000 JOD."),
        ]
    )
    await db_session.commit()

    batches: list[list[str]] = []

    def summarize(_previous_summary, messages, **_kwargs):
        batches.append([message.content for message in messages])
        return "Known facts:\n- Salary: 20000 JOD.\n- Married scenario discussed."

    monkeypatch.setattr(memory, "generate_memory_summary", summarize)

    real_persist = memory.persist_memory_summary_if_fresh
    persist_calls = 0

    async def stale_once(session_id, expected_message_count, new_summary, new_message_count):
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 1:
            async with TestSessionFactory() as db:
                existing = await db.get(ChatSession, session_id)
                existing.memory_summary = "Known facts:\n- Salary: 20000 JOD."
                existing.memory_message_count = 2
                await db.commit()
            return False
        return await real_persist(
            session_id,
            expected_message_count,
            new_summary,
            new_message_count,
        )

    monkeypatch.setattr(memory, "persist_memory_summary_if_fresh", stale_once)

    await memory.refresh_session_memory(session.id, lang="en", preferred_provider="gemini")
    await db_session.refresh(session)

    assert batches[0] == [
        "Salary 20000 JOD",
        "Noted.",
        "What if married?",
        "Using salary 20000 JOD.",
    ]
    assert batches[1] == ["What if married?", "Using salary 20000 JOD."]
    assert session.memory_message_count == 4
    assert "Married scenario discussed" in (session.memory_summary or "")
