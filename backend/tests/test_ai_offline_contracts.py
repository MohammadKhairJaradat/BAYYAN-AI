"""Offline AI Provider and No-Key Contract Regression Tests (Card G-AI-OFFLINE01).

Tests capabilities.ai reporting, Premium Gemini model gating, missing-provider 503
prior to session/quota creation, provider error classification, and stable error mapping.
All tests use fake/mocked providers only — zero real API keys or external network calls.
"""

from unittest.mock import MagicMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api import rag as rag_module
from app.config import settings
from app.integrations.ai import adapters
from app.models.database import ChatSession, User


SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"

USER_DATA = {
    "username": "offline_tester@example.com",
    "password": "Password123!",
    "name": "Offline Tester",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(client: AsyncClient, user_data: dict) -> str:
    signup_res = await client.post(SIGNUP_URL, json=user_data)
    assert signup_res.status_code == 201, signup_res.text
    login_res = await client.post(
        LOGIN_URL,
        json={"username": user_data["username"], "password": user_data["password"]},
    )
    assert login_res.status_code == 200, login_res.text
    return login_res.json()["access_token"]


async def _set_tier(db_session: AsyncSession, username: str, tier: str) -> None:
    res = await db_session.execute(select(User).where(User.username == username))
    user = res.scalar_one()
    user.subscription_tier = tier
    await db_session.commit()


# ── 1. /capabilities.ai contract & fallback tests ───────────────────────────

@pytest.mark.asyncio
async def test_capabilities_ai_reports_empty_when_no_keys_configured(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "ADVISOR_LLM_PROVIDER", "gemini")

    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    ai = response.json()["ai"]
    assert ai["configured_providers"] == []
    assert ai["document_extraction"] is False
    assert ai["advisor"] is False
    assert ai["voice"] is False


@pytest.mark.asyncio
async def test_capabilities_ai_google_fallback_key_detection(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # Only GOOGLE_AI_API_KEY is provided (voice and extraction fallback)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GOOGLE_AI_API_KEY", "fake-google-key-secret")
    monkeypatch.setattr(settings, "ADVISOR_LLM_PROVIDER", "gemini")

    response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    ai = response.json()["ai"]
    assert "gemini" in ai["configured_providers"]
    assert ai["document_extraction"] is True
    assert ai["voice"] is True
    assert ai["advisor"] is True
    # Crucially ensure the secret value never leaks in public output
    assert "fake-google-key-secret" not in response.text


# ── 2. Premium Gemini model access & tier-boundary rejection ─────────────────

@pytest.mark.asyncio
async def test_gemini_2_5_pro_gated_by_tier(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(rag_module, "provider_is_configured", lambda _p: True)

    captured_tokens = []

    def mock_answer(*_a, **kwargs):
        captured_tokens.append(kwargs.get("max_tokens"))
        return {
            "answer": "Pro response",
            "sources": [],
            "provider": "gemini",
            "model": "gemini-2.5-pro",
        }

    monkeypatch.setattr(rag_module, "qa_answer", mock_answer)

    token = await _signup_and_login(client, USER_DATA)

    # 1. Basic user requesting gemini-2.5-pro -> 403 Forbidden
    res_basic = await client.post(
        "/api/v1/rag/chat",
        json={"question": "Hello", "provider": "gemini", "model": "gemini-2.5-pro"},
        headers=_auth(token),
    )
    assert res_basic.status_code == 403
    assert "not available on your Basic plan" in res_basic.json()["detail"]

    # 2. Pro user requesting gemini-2.5-pro -> 403 Forbidden
    await _set_tier(db_session, USER_DATA["username"], "Pro")
    res_pro = await client.post(
        "/api/v1/rag/chat",
        json={"question": "Hello", "provider": "gemini", "model": "gemini-2.5-pro"},
        headers=_auth(token),
    )
    assert res_pro.status_code == 403
    assert "not available on your Pro plan" in res_pro.json()["detail"]

    # 3. Premium user requesting gemini-2.5-pro -> 200 OK with 4096 max_tokens
    await _set_tier(db_session, USER_DATA["username"], "Premium")
    res_prem = await client.post(
        "/api/v1/rag/chat",
        json={"question": "Hello", "provider": "gemini", "model": "gemini-2.5-pro"},
        headers=_auth(token),
    )
    assert res_prem.status_code == 200, res_prem.text
    body = res_prem.json()
    assert body["provider"] == "gemini"
    assert body["model"] == "gemini-2.5-pro"
    assert captured_tokens[-1] == 4096


# ── 3. Missing provider 503 before session creation or quota reservation ─────

@pytest.mark.asyncio
async def test_missing_provider_503_fails_before_session_or_quota(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(rag_module, "provider_is_configured", lambda _p: False)
    unique_user = {**USER_DATA, "username": "no_key_user", "email": "nokey@example.com"}
    token = await _signup_and_login(client, unique_user)

    res = await client.post(
        "/api/v1/rag/chat",
        json={"question": "What is tax rate?", "provider": "gemini", "model": "gemini-2.5-flash"},
        headers=_auth(token),
    )
    assert res.status_code == 503
    assert "gemini is not configured for chat" in res.json()["detail"]

    # Zero sessions created
    sessions = (await client.get("/api/v1/chat/sessions", headers=_auth(token))).json()
    assert sessions == []

    # Zero quota messages used
    usage = (await client.get("/api/v1/users/me/usage", headers=_auth(token))).json()
    assert usage["messages"]["used"] == 0


# ── 4. Provider timeout and error classification ─────────────────────────────

def test_ai_provider_error_classification():
    # 1. Rate limits / Resource exhaustion
    err_429 = RuntimeError("Rate limit exceeded")
    err_429.status_code = 429
    assert adapters._provider_error("gemini", err_429).kind == "rate_limit"

    class ResourceExhaustedError(Exception):
        pass

    assert adapters._provider_error("gemini", ResourceExhaustedError("Quota")).kind == "rate_limit"

    # 2. Timeouts
    timeout_err = TimeoutError("Request timed out")
    assert adapters._provider_error("openai", timeout_err).kind == "timeout"

    class APITimeoutError(Exception):
        pass

    assert adapters._provider_error("anthropic", APITimeoutError("deadline")).kind == "timeout"

    # 3. Bad requests (400, 422)
    err_400 = ValueError("Invalid prompt")
    err_400.status_code = 400
    assert adapters._provider_error("groq", err_400).kind == "bad_request"

    # 4. General unavailabilities
    assert adapters._provider_error("gemini", RuntimeError("Unknown internal crash")).kind == "unavailable"

    # 5. String representation does not include credentials
    prov_err = adapters.AIProviderError(provider="gemini", kind="timeout", status_code=504)
    assert str(prov_err) == "gemini timeout"


# ── 5. Stable user-visible Chat error mapping on LLM failure ─────────────────

@pytest.mark.asyncio
async def test_chat_stable_error_mapping_on_provider_failure(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(rag_module, "provider_is_configured", lambda _p: True)

    def raise_provider_timeout(*_a, **_kw):
        raise TimeoutError("Simulated upstream provider timeout")

    monkeypatch.setattr(rag_module, "qa_answer", raise_provider_timeout)

    unique_user = {**USER_DATA, "username": "timeout_user", "email": "timeout@example.com"}
    token = await _signup_and_login(client, unique_user)

    res = await client.post(
        "/api/v1/rag/chat",
        json={"question": "Help me with taxes", "provider": "gemini", "model": "gemini-2.5-flash"},
        headers=_auth(token),
    )

    # Must return 200 OK so UI displays error gracefully without app crash
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["provider"] == "error"
    assert body["model"] is None
    assert body["answer"] == rag_module._LLM_FAILURE_MESSAGE
    sid = body["session_id"]
    assert sid

    # Verify session and both messages exist in history
    session_data = (await client.get(f"/api/v1/chat/sessions/{sid}", headers=_auth(token))).json()
    assert len(session_data["messages"]) == 2
    assert session_data["messages"][0]["role"] == "user"
    assert session_data["messages"][0]["content"] == "Help me with taxes"
    assert session_data["messages"][1]["role"] == "assistant"
    assert session_data["messages"][1]["content"] == rag_module._LLM_FAILURE_MESSAGE
