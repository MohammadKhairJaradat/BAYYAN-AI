"""Tests for the LangGraph advisor pipeline.

External services (LLM, RAG retrieval) are monkey-patched so the suite does
not require an Anthropic key, ChromaDB, or the 2 GB embedding model.
"""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.advisor import nodes as advisor_nodes

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
TAX_PROFILES_URL = "/api/v1/tax-profiles/"
INCOME_SOURCES_URL = "/api/v1/income-sources/"
DEDUCTIONS_URL = "/api/v1/deductions/"


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


async def _create_profile(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {
        # user_id is overwritten server-side from the token
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2025,
        "marital_status": "married",
        "num_dependents": 2,
    }
    payload.update(overrides)
    resp = await client.post(TAX_PROFILES_URL, json=payload, headers=_auth(token))
    return resp.json()


async def _add_income(client: AsyncClient, token: str, profile_id: str, amount: float = 30000.0) -> dict:
    resp = await client.post(
        INCOME_SOURCES_URL,
        json={
            "tax_profile_id": profile_id,
            "type": "salary",
            "amount": str(amount),
            "employer_name": "Acme",
        },
        headers=_auth(token),
    )
    return resp.json()


async def _add_deduction(
    client: AsyncClient,
    token: str,
    profile_id: str,
    category: str = "medical",
    amount: float = 500.0,
) -> dict:
    resp = await client.post(
        DEDUCTIONS_URL,
        json={
            "tax_profile_id": profile_id,
            "category": category,
            "amount": str(amount),
        },
        headers=_auth(token),
    )
    return resp.json()


# ── Test doubles ────────────────────────────────────────────────────────────


class _LLMSpy:
    """Records every call; returns canned JSON keyed by which system prompt arrives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.canned: dict[str, dict[str, Any]] = {
            "deductions": {
                "opportunities": [
                    {
                        "category": "housing_interest",
                        "description": "You may have unclaimed housing interest.",
                        "estimated_savings": 200.0,
                        "citation": "Article 20",
                    }
                ],
                "narrative": "You appear to be missing housing-interest deductions.",
            },
            "risk": {
                "flags": [
                    {
                        "severity": "low",
                        "issue": "Salary income reported without a salary slip.",
                        "suggestion": "Upload your latest salary slip.",
                    }
                ],
                "narrative": "Documentation is incomplete for salary income.",
            },
            "plan": {
                "steps": [
                    {
                        "priority": 1,
                        "action": "Upload missing salary slip.",
                        "description": "Required to substantiate salary income.",
                    },
                    {
                        "priority": 2,
                        "action": "Claim housing-interest deduction.",
                    },
                ],
                "narrative": "Two priority actions to reduce risk and tax owed.",
            },
        }

    async def __call__(self, system: str, user: str, **_kw) -> dict[str, Any]:
        self.calls.append((system, user))
        if "Identify missed" in system or "missed or under-claimed" in user:
            return self.canned["deductions"]
        if "assess audit risk" in system or "audit risks" in user:
            return self.canned["risk"]
        if "action plan" in system or "prioritized action plan" in user:
            return self.canned["plan"]
        # Fall back by call order
        order = ["deductions", "risk", "plan"]
        idx = min(len(self.calls) - 1, len(order) - 1)
        return self.canned[order[idx]]


def _fake_retrieve(*_args, **_kwargs):
    return ([], "")


@pytest.fixture
def llm_spy(monkeypatch: pytest.MonkeyPatch) -> _LLMSpy:
    spy = _LLMSpy()
    monkeypatch.setattr(advisor_nodes, "complete_json", spy)
    monkeypatch.setattr(advisor_nodes, "retrieve_with_context", _fake_retrieve)
    return spy


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_full_report(client: AsyncClient, llm_spy: _LLMSpy):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=30000.0)
    await _add_deduction(client, token, profile["id"], category="medical", amount=500.0)

    resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "ar"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "complete"
    assert data["lang"] == "ar"
    assert data["missing_fields"] == []

    # baseline tax was computed deterministically
    assert data["baseline"] is not None
    assert data["baseline"]["gross_income"] == 30000.0
    assert data["baseline"]["tax_liability"] >= 0

    # tax_engine.model_scenarios auto-generates 3 scenarios
    assert len(data["scenarios"]) == 3
    labels = {s["label"] for s in data["scenarios"]}
    # the scenarios are bilingual labels; assert the count and shape rather than exact text
    for s in data["scenarios"]:
        assert "tax_liability" in s
        assert "delta_vs_baseline" in s

    # LLM nodes produced their canned output
    assert data["deduction_opportunities"][0]["category"] == "housing_interest"
    assert data["risk_flags"][0]["severity"] == "low"
    assert data["action_plan"][0]["priority"] == 1
    assert data["narratives"]["plan"].startswith("Two priority")

    # All three LLM nodes ran exactly once
    assert len(llm_spy.calls) == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_incomplete_profile_short_circuits(client: AsyncClient, llm_spy: _LLMSpy):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    # Intentionally do NOT add an income source

    resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "en"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "incomplete"
    assert "income_sources" in data["missing_fields"]
    assert data["lang"] == "en"
    assert data["baseline"] is None
    assert data["scenarios"] == []

    # No LLM calls should have been made
    assert llm_spy.calls == []


@pytest.mark.asyncio
async def test_other_users_profile_returns_404(client: AsyncClient, llm_spy: _LLMSpy):
    token_a = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token_a)
    await _add_income(client, token_a, profile["id"])

    token_b = await _signup_and_login(client, USER_B)
    resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        headers=_auth(token_b),
    )
    assert resp.status_code == 404
    assert llm_spy.calls == []


@pytest.mark.asyncio
async def test_latest_report_is_null_before_first_run(
    client: AsyncClient, llm_spy: _LLMSpy
):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)

    resp = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() is None
    assert llm_spy.calls == []


@pytest.mark.asyncio
async def test_latest_report_survives_fresh_login(
    client: AsyncClient, llm_spy: _LLMSpy
):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=30000.0)

    run_resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "ar"},
        headers=_auth(token),
    )
    assert run_resp.status_code == 200, run_resp.text

    login_resp = await client.post(
        LOGIN_URL,
        json={"username": USER_A["username"], "password": USER_A["password"]},
    )
    fresh_token = login_resp.json()["access_token"]

    latest_resp = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(fresh_token),
    )
    assert latest_resp.status_code == 200, latest_resp.text
    latest = latest_resp.json()

    assert latest["is_stale"] is False
    assert latest["report"]["status"] == "complete"
    assert latest["report"]["lang"] == "ar"
    assert latest["report"]["baseline"]["gross_income"] == 30000.0


@pytest.mark.asyncio
async def test_second_run_overwrites_latest_report(
    client: AsyncClient, llm_spy: _LLMSpy
):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=30000.0)

    first = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "ar"},
        headers=_auth(token),
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "en"},
        headers=_auth(token),
    )
    assert second.status_code == 200, second.text

    latest_resp = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(token),
    )
    latest = latest_resp.json()

    assert latest_resp.status_code == 200, latest_resp.text
    assert latest["report"]["lang"] == "en"
    assert latest["is_stale"] is False


@pytest.mark.asyncio
async def test_latest_report_marks_stale_after_profile_inputs_change(
    client: AsyncClient, llm_spy: _LLMSpy
):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=30000.0)

    run_resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        headers=_auth(token),
    )
    assert run_resp.status_code == 200, run_resp.text

    before = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(token),
    )
    assert before.json()["is_stale"] is False

    await _add_deduction(
        client,
        token,
        profile["id"],
        category="education",
        amount=800.0,
    )

    after = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(token),
    )
    assert after.status_code == 200, after.text
    assert after.json()["is_stale"] is True


@pytest.mark.asyncio
async def test_latest_report_is_user_scoped(client: AsyncClient, llm_spy: _LLMSpy):
    token_a = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token_a)
    await _add_income(client, token_a, profile["id"])

    run_resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        headers=_auth(token_a),
    )
    assert run_resp.status_code == 200, run_resp.text

    token_b = await _signup_and_login(client, USER_B)
    latest_resp = await client.get(
        f"/api/v1/advisor/{profile['id']}/latest",
        headers=_auth(token_b),
    )

    assert latest_resp.status_code == 404


@pytest.mark.asyncio
async def test_llm_failure_is_soft(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """If a single LLM node raises, downstream nodes still run and the error is reported."""

    monkeypatch.setattr(advisor_nodes, "retrieve_with_context", _fake_retrieve)

    call_order: list[str] = []

    async def flaky_complete(system: str, user: str, **_kw):
        if "missed or under-claimed" in user or "Identify missed" in system:
            call_order.append("deductions:FAIL")
            raise RuntimeError("boom")
        if "audit risks" in user or "assess audit risk" in system:
            call_order.append("risk")
            return {"flags": [], "narrative": "no issues"}
        call_order.append("plan")
        return {"steps": [], "narrative": "minimal plan"}

    monkeypatch.setattr(advisor_nodes, "complete_json", flaky_complete)

    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"])

    resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "complete"
    # Deductions node failed but downstream ran
    assert any(e.startswith("deductions:") for e in data["errors"])
    assert call_order[0] == "deductions:FAIL"
    assert "risk" in call_order
    assert "plan" in call_order

    # Baseline + scenarios still produced (deterministic, not affected by LLM)
    assert data["baseline"] is not None
    assert len(data["scenarios"]) == 3


@pytest.mark.asyncio
async def test_plan_parse_failure_returns_deterministic_fallback(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Malformed LLM JSON should not leave the advisor with an empty plan."""

    monkeypatch.setattr(advisor_nodes, "retrieve_with_context", _fake_retrieve)

    async def parse_fails_for_plan(system: str, user: str, **_kw):
        if "missed or under-claimed" in user or "Identify missed" in system:
            return {"opportunities": [], "narrative": "No deduction gaps found."}
        if "audit risks" in user or "assess audit risk" in system:
            return {"flags": [], "narrative": "No major risks found."}
        return {"error": "parse_failed", "raw": '{"steps": ['}

    monkeypatch.setattr(advisor_nodes, "complete_json", parse_fails_for_plan)

    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=30000.0)

    resp = await client.post(
        f"/api/v1/advisor/{profile['id']}/run",
        json={"lang": "en"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["status"] == "complete"
    assert "plan:llm_parse_failed" in data["errors"]
    assert data["action_plan"]
    assert data["action_plan"][0]["priority"] == 1
    assert "salary slip" in data["action_plan"][0]["action"].lower()
    assert data["narratives"]["plan"].startswith("I could not parse")
