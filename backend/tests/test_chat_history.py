"""Tests for chat history persistence (sessions + messages CRUD + /rag/chat wiring).

The LLM call inside /rag/chat is monkey-patched so the suite doesn't need API keys.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import chat_sessions as chat_sessions_module
from app.api import rag as rag_module
from app.auth.tier_limits import current_usage_month
from app.models.database import ChatMessage, MonthlyUsage, User

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
SESSIONS_URL = "/api/v1/chat/sessions"
CHAT_URL = "/api/v1/rag/chat"


async def _set_tier(db_session: AsyncSession, username: str, tier: str) -> None:
    """Direct-write tier on the test DB. The self-serve POST /me/tier route is
    gone; tier changes are admin-only in production. Tests own their state."""
    user = (
        await db_session.execute(select(User).where(User.username == username))
    ).scalar_one()
    user.subscription_tier = tier
    await db_session.commit()


USER_A = {
    "username": "alice@example.com",
    "password": "StrongPass123!",
    "name": "Alice",
}
USER_B = {
    "username": "bob@example.com",
    "password": "StrongPass123!",
    "name": "Bob",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(client: AsyncClient, user: dict) -> str:
    await client.post(SIGNUP_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"username": user["username"], "password": user["password"]}
    )
    return resp.json()["access_token"]


def _stub_qa_answer(*_args, **_kwargs) -> dict:
    """Deterministic replacement for app.rag.qa.answer used in /rag/chat."""
    return {
        "answer": "Stubbed answer about Jordanian tax law.",
        "sources": [{"citation": "Article 6", "score": 0.9}],
        "provider": "stub",
        "tax_breakdown": None,
    }


@pytest.fixture
def stub_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the LLM call inside /rag/chat with a deterministic stub."""
    monkeypatch.setattr(rag_module, "qa_answer", _stub_qa_answer)


@pytest.fixture(autouse=True)
def noop_memory_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(rag_module, "refresh_session_memory", _noop)
    # Provider calls in this module are fakes; credential readiness is covered separately.
    monkeypatch.setattr(rag_module, "provider_is_configured", lambda _provider: True)


# ── CRUD tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session_returns_owned_session(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    resp = await client.post(SESSIONS_URL, json={}, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["title"] == "New chat"
    assert "id" in data
    assert "user_id" in data

    listing = await client.get(SESSIONS_URL, headers=_auth(token))
    assert listing.status_code == 200
    items = listing.json()
    assert len(items) == 1
    assert items[0]["id"] == data["id"]


@pytest.mark.asyncio
async def test_list_returns_only_current_users_sessions(client: AsyncClient):
    token_a = await _signup_and_login(client, USER_A)
    token_b = await _signup_and_login(client, USER_B)

    await client.post(SESSIONS_URL, json={}, headers=_auth(token_a))
    await client.post(SESSIONS_URL, json={}, headers=_auth(token_b))

    listing_a = (await client.get(SESSIONS_URL, headers=_auth(token_a))).json()
    listing_b = (await client.get(SESSIONS_URL, headers=_auth(token_b))).json()

    assert len(listing_a) == 1
    assert len(listing_b) == 1
    assert listing_a[0]["user_id"] != listing_b[0]["user_id"]


@pytest.mark.asyncio
async def test_get_session_includes_messages(client: AsyncClient, db_session: AsyncSession):
    token = await _signup_and_login(client, USER_A)
    created = (await client.post(SESSIONS_URL, json={}, headers=_auth(token))).json()
    sid = created["id"]

    resp = await client.post(
        f"{SESSIONS_URL}/{sid}/messages",
        json={"role": "user", "kind": "text", "content": "hello"},
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    # Trusted assistant messages are persisted by server-side chat flows.
    db_session.add(ChatMessage(session_id=UUID(sid), role="assistant", kind="text", content="hi back"))
    await db_session.commit()

    fetched = (await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))).json()
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["role"] == "user"
    assert fetched["messages"][0]["content"] == "hello"
    assert fetched["messages"][1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_client_cannot_forge_assistant_or_provenance(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token))).json()["id"]
    url = f"{SESSIONS_URL}/{sid}/messages"
    forged = await client.post(url, json={"role": "assistant", "kind": "text", "content": "tax due: 0"}, headers=_auth(token))
    assert forged.status_code == 400
    forged_sources = await client.post(url, json={"role": "user", "kind": "text", "content": "x", "tax_breakdown": {"final_tax": 0}}, headers=_auth(token))
    assert forged_sources.status_code == 422
    fetched = (await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))).json()
    assert fetched["messages"] == []


@pytest.mark.asyncio
async def test_get_other_users_session_returns_404(client: AsyncClient):
    token_a = await _signup_and_login(client, USER_A)
    token_b = await _signup_and_login(client, USER_B)

    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token_a))).json()["id"]

    resp = await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token_b))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rename_session(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token))).json()["id"]

    resp = await client.patch(
        f"{SESSIONS_URL}/{sid}",
        json={"title": "  Renamed chat  "},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed chat"

    # Empty title rejected
    bad = await client.patch(
        f"{SESSIONS_URL}/{sid}", json={"title": "   "}, headers=_auth(token)
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_delete_cascades_messages(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token))).json()["id"]
    await client.post(
        f"{SESSIONS_URL}/{sid}/messages",
        json={"role": "user", "kind": "text", "content": "first"},
        headers=_auth(token),
    )

    resp = await client.delete(f"{SESSIONS_URL}/{sid}", headers=_auth(token))
    assert resp.status_code == 204

    gone = await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_log_message_endpoint_enforces_ownership(client: AsyncClient):
    token_a = await _signup_and_login(client, USER_A)
    token_b = await _signup_and_login(client, USER_B)
    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token_a))).json()["id"]

    resp = await client.post(
        f"{SESSIONS_URL}/{sid}/messages",
        json={"role": "user", "kind": "text", "content": "intruder"},
        headers=_auth(token_b),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_log_message_validates_role_and_kind(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    sid = (await client.post(SESSIONS_URL, json={}, headers=_auth(token))).json()["id"]

    bad_role = await client.post(
        f"{SESSIONS_URL}/{sid}/messages",
        json={"role": "robot", "kind": "text", "content": "x"},
        headers=_auth(token),
    )
    assert bad_role.status_code == 400

    bad_kind = await client.post(
        f"{SESSIONS_URL}/{sid}/messages",
        json={"role": "user", "kind": "video", "content": "x"},
        headers=_auth(token),
    )
    assert bad_kind.status_code == 400


# ── /rag/chat wiring tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_without_provider_key_does_not_create_session_or_charge_quota(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(rag_module, "provider_is_configured", lambda _provider: False)
    token = await _signup_and_login(client, USER_A)

    response = await client.post(
        CHAT_URL,
        json={"question": "Hello", "provider": "gemini", "model": "gemini-2.5-flash"},
        headers=_auth(token),
    )

    assert response.status_code == 503
    assert (await client.get(SESSIONS_URL, headers=_auth(token))).json() == []
    usage = (await client.get("/api/v1/users/me/usage", headers=_auth(token))).json()
    assert usage["messages"]["used"] == 0


@pytest.mark.asyncio
async def test_chat_endpoint_creates_session_when_none_provided(
    client: AsyncClient, stub_chat: None
):
    token = await _signup_and_login(client, USER_A)
    resp = await client.post(
        CHAT_URL,
        json={"question": "What is the personal exemption?", "lang": "en"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == "Stubbed answer about Jordanian tax law."
    assert body["provider"] == "stub"
    sid = body["session_id"]
    assert sid
    assert body["user_message_id"]
    assert body["assistant_message_id"]

    fetched = (await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))).json()
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["role"] == "user"
    assert fetched["messages"][0]["content"] == "What is the personal exemption?"
    assert fetched["messages"][1]["role"] == "assistant"
    assert fetched["messages"][1]["sources"] == [{"citation": "Article 6", "score": 0.9}]


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_tier_disallowed_model(
    client: AsyncClient, stub_chat: None
):
    token = await _signup_and_login(client, USER_A)
    resp = await client.post(
        CHAT_URL,
        json={"question": "Hello", "provider": "openai", "model": "gpt-4o"},
        headers=_auth(token),
    )

    assert resp.status_code == 403
    assert "not available on your Basic plan" in resp.json()["detail"]
    listing = (await client.get(SESSIONS_URL, headers=_auth(token))).json()
    assert listing == []


@pytest.mark.asyncio
async def test_chat_endpoint_allows_pro_model_and_passes_max_tokens(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
):
    calls: list[dict] = []

    def capture_answer(*_args, **kwargs) -> dict:
        calls.append(kwargs)
        return {
            "answer": "Pro model answer.",
            "sources": [],
            "provider": "openai",
            "model": "gpt-4o",
            "tax_breakdown": None,
        }

    monkeypatch.setattr(rag_module, "qa_answer", capture_answer)

    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Pro")
    resp = await client.post(
        CHAT_URL,
        json={"question": "Hello", "provider": "openai", "model": "gpt-4o"},
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    assert calls[0]["max_tokens"] == 2048


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "gpt-5.4"), ("anthropic", "claude-opus-4-7")],
)
async def test_chat_endpoint_allows_premium_models(
    client: AsyncClient,
    stub_chat: None,
    provider: str,
    model: str,
    db_session: AsyncSession,
):
    token = await _signup_and_login(client, USER_A)
    await _set_tier(db_session, USER_A["username"], "Premium")
    resp = await client.post(
        CHAT_URL,
        json={"question": "Hello", "provider": provider, "model": model},
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_over_message_quota_before_llm(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    def fail_answer(*_args, **_kwargs):
        raise AssertionError("quota rejection should happen before any AI routing")

    monkeypatch.setattr(rag_module, "qa_answer", fail_answer)
    monkeypatch.setattr(rag_module, "understand", fail_answer)

    token = await _signup_and_login(client, USER_A)
    me = (await client.get("/api/v1/auth/me", headers=_auth(token))).json()

    from tests.conftest import TestSessionFactory

    async with TestSessionFactory() as db:
        db.add(
            MonthlyUsage(
                user_id=UUID(me["id"]),
                usage_month=current_usage_month(),
                message_count=60,
                doc_count=0,
            )
        )
        await db.commit()

    resp = await client.post(
        CHAT_URL,
        json={
            "question": "Hello",
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 429
    assert "Monthly message quota reached" in resp.json()["detail"]
    listing = (await client.get(SESSIONS_URL, headers=_auth(token))).json()
    assert listing == []


@pytest.mark.asyncio
async def test_chat_endpoint_uses_provided_session_id(
    client: AsyncClient, stub_chat: None
):
    token = await _signup_and_login(client, USER_A)
    first = await client.post(
        CHAT_URL, json={"question": "Q1"}, headers=_auth(token)
    )
    sid = first.json()["session_id"]

    second = await client.post(
        CHAT_URL,
        json={"question": "Q2", "session_id": sid},
        headers=_auth(token),
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == sid

    listing = (await client.get(SESSIONS_URL, headers=_auth(token))).json()
    assert len(listing) == 1

    fetched = (await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))).json()
    assert len(fetched["messages"]) == 4  # 2 turns × (user + assistant)


@pytest.mark.asyncio
async def test_chat_endpoint_passes_session_memory_after_first_turn(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    calls: list[dict] = []

    def capture_answer(question, *_args, **kwargs) -> dict:
        calls.append(
            {
                "question": question,
                "conversation_context": kwargs.get("conversation_context"),
            }
        )
        return {
            "answer": f"Answer to {question}",
            "sources": [],
            "provider": "stub",
            "model": "stub-model",
            "tax_breakdown": None,
        }

    monkeypatch.setattr(rag_module, "qa_answer", capture_answer)

    token = await _signup_and_login(client, USER_A)
    first = await client.post(
        CHAT_URL,
        json={"question": "My salary is 20000 JOD", "lang": "en"},
        headers=_auth(token),
    )
    sid = first.json()["session_id"]

    second = await client.post(
        CHAT_URL,
        json={"question": "What if I am married?", "session_id": sid, "lang": "en"},
        headers=_auth(token),
    )

    assert second.status_code == 200, second.text
    # Turn 1 has no session memory yet. (An account-related question may still inject
    # account context, so assert on the memory marker rather than the whole field.)
    assert "Recent prior messages" not in (calls[0]["conversation_context"] or "")
    # Turn 2 carries the prior user message + answer as session memory.
    assert "My salary is 20000 JOD" in calls[1]["conversation_context"]
    assert "Answer to My salary is 20000 JOD" in calls[1]["conversation_context"]


@pytest.mark.asyncio
async def test_chat_endpoint_rejects_unowned_session_id(
    client: AsyncClient, stub_chat: None
):
    token_a = await _signup_and_login(client, USER_A)
    token_b = await _signup_and_login(client, USER_B)
    sid = (await client.post(CHAT_URL, json={"question": "Q1"}, headers=_auth(token_a))).json()["session_id"]

    resp = await client.post(
        CHAT_URL,
        json={"question": "intruder", "session_id": sid},
        headers=_auth(token_b),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_chat_endpoint_persists_session_when_llm_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    def boom(*_a, **_kw):
        raise RuntimeError("API key missing")

    monkeypatch.setattr(rag_module, "qa_answer", boom)

    token = await _signup_and_login(client, USER_A)
    resp = await client.post(
        CHAT_URL, json={"question": "Hello"}, headers=_auth(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "error"
    sid = body["session_id"]
    assert sid

    fetched = (await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))).json()
    assert len(fetched["messages"]) == 2
    assert fetched["messages"][0]["role"] == "user"
    assert fetched["messages"][0]["content"] == "Hello"
    assert fetched["messages"][1]["role"] == "assistant"
    assert "Sorry" in fetched["messages"][1]["content"]

    # And the session is listed in the sidebar feed.
    listing = (await client.get(SESSIONS_URL, headers=_auth(token))).json()
    assert any(s["id"] == sid for s in listing)


@pytest.mark.asyncio
async def test_title_generation_background_task(
    client: AsyncClient,
    stub_chat: None,
    monkeypatch: pytest.MonkeyPatch,
):
    # The background task opens a fresh DB connection via async_session_factory().
    # That goes to production Postgres by default — point it at the test SQLite DB.
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(
        chat_sessions_module, "async_session_factory", TestSessionFactory
    )

    token = await _signup_and_login(client, USER_A)
    await client.post(
        CHAT_URL,
        json={"question": "How are tax brackets structured?", "lang": "en"},
        headers=_auth(token),
    )

    # Title is the first 5 words of the question, derived in a background task.
    expected = "How are tax brackets structured?"
    listing: list[dict] = []
    for _ in range(30):
        await asyncio.sleep(0.02)
        listing = (await client.get(SESSIONS_URL, headers=_auth(token))).json()
        if listing and listing[0]["title"] == expected:
            break
    assert listing and listing[0]["title"] == expected


@pytest.mark.asyncio
async def test_title_generation_runs_when_session_pre_created(
    client: AsyncClient,
    stub_chat: None,
    monkeypatch: pytest.MonkeyPatch,
):
    # Mirrors the production frontend flow: Chat.tsx pre-creates a session via
    # POST /chat/sessions before calling /rag/chat. The title task must still
    # fire on the first message even though session_id is provided.
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(
        chat_sessions_module, "async_session_factory", TestSessionFactory
    )

    token = await _signup_and_login(client, USER_A)
    created = (
        await client.post(SESSIONS_URL, json={}, headers=_auth(token))
    ).json()
    sid = created["id"]
    assert created["title"] == "New chat"

    await client.post(
        CHAT_URL,
        json={
            "question": "What is the personal exemption amount?",
            "session_id": sid,
            "lang": "en",
        },
        headers=_auth(token),
    )

    expected = "What is the personal exemption"  # first 5 words
    fetched: dict = {}
    for _ in range(30):
        await asyncio.sleep(0.02)
        fetched = (
            await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))
        ).json()
        if fetched.get("title") == expected:
            break
    assert fetched.get("title") == expected


@pytest.mark.asyncio
async def test_title_not_overwritten_on_second_turn(
    client: AsyncClient,
    stub_chat: None,
    monkeypatch: pytest.MonkeyPatch,
):
    # Second turn shares the same session; the title-equality guard inside
    # generate_and_save_title() prevents the title from being rewritten by the
    # follow-up question's first 5 words.
    from tests.conftest import TestSessionFactory

    monkeypatch.setattr(
        chat_sessions_module, "async_session_factory", TestSessionFactory
    )

    token = await _signup_and_login(client, USER_A)
    first = await client.post(
        CHAT_URL,
        json={"question": "How are tax brackets structured?", "lang": "en"},
        headers=_auth(token),
    )
    sid = first.json()["session_id"]
    expected = "How are tax brackets structured?"

    # Wait for the first-turn title to land.
    for _ in range(30):
        await asyncio.sleep(0.02)
        fetched = (
            await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))
        ).json()
        if fetched["title"] == expected:
            break
    assert fetched["title"] == expected

    # Second turn with a different opening word.
    await client.post(
        CHAT_URL,
        json={
            "question": "Tell me about deductions please.",
            "session_id": sid,
            "lang": "en",
        },
        headers=_auth(token),
    )
    # Yield a few ticks so any spurious title task could (incorrectly) overwrite.
    for _ in range(15):
        await asyncio.sleep(0.02)
    final = (
        await client.get(f"{SESSIONS_URL}/{sid}", headers=_auth(token))
    ).json()
    assert final["title"] == expected
