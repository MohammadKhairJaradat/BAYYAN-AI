"""Tests for the chat understanding layer: parsing, slot merge, contradictions,
fallback, and the end-to-end carry-forward + contradiction behavior."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.models import MaritalStatus
from app.rag import qa
from app.rag.account_context import build_profile_updates, merge_tax_inputs
from app.rag.prompts_understanding import UNDERSTANDING_SYSTEM_PROMPT
from app.rag.understanding import (
    _coerce_stated,
    _is_trivial_greeting,
    _parse_understanding,
    understand,
)
from app.tax_engine import TaxInput, calculate_tax

from tests.test_account_chat_context import (
    CHAT_URL,
    MODEL,
    PROVIDER,
    _add_income,
    _auth,
    _create_profile,
    _signup_and_login,
)


# ── Parsing / coercion ──────────────────────────────────────────────────────


def test_parse_understanding_ok():
    u = _parse_understanding(
        '{"intent":"tax_calculation","stated":{"gross_income":50000,'
        '"marital_status":"married"},"reasoning":"x"}'
    )
    assert u is not None
    assert u.intent == "tax_calculation"
    assert u.stated["gross_income"] == 50000
    assert u.stated["marital_status"] == "married"
    assert u.source == "llm"


def test_parse_understanding_strips_code_fences():
    u = _parse_understanding('```json\n{"intent":"off_topic","stated":{}}\n```')
    assert u is not None and u.intent == "off_topic"


def test_parse_understanding_invalid_returns_none():
    assert _parse_understanding("not json at all") is None
    assert _parse_understanding('{"intent":"banana","stated":{}}') is None
    assert _parse_understanding("") is None


def test_coerce_stated_drops_bad_values():
    stated = _coerce_stated(
        {
            "gross_income": "abc",  # not numeric → dropped
            "marital_status": "divorced",  # invalid → dropped
            "num_dependents": 2,
            "deductions": [
                {"category": "medical", "amount": 100},
                {"category": "bogus", "amount": 5},  # invalid category → dropped
            ],
        }
    )
    assert "gross_income" not in stated
    assert "marital_status" not in stated
    assert stated["num_dependents"] == 2
    assert stated["deductions"] == [{"category": "medical", "amount": 100.0}]


def test_trivial_greeting_rejects_tax_and_long_text():
    assert not _is_trivial_greeting("احسب ضريبتي دخلي 50000 دينار")
    assert not _is_trivial_greeting("")
    assert not _is_trivial_greeting("x" * 60)


def test_understand_falls_back_to_none_on_llm_error(monkeypatch):
    def boom(*_a, **_kw):
        raise RuntimeError("no API key")

    monkeypatch.setattr(qa, "_call_llm", boom)
    # Contains a tax keyword so the fast-path is skipped and the LLM is attempted.
    result = understand("what is my tax on my salary?", None, None, provider="anthropic")
    assert result is None


# ── Slot merge (carry-forward + married convention) ─────────────────────────


def test_merge_carries_income_and_applies_married_flags():
    base = TaxInput(gross_income=20000)
    merged = merge_tax_inputs(base, {"gross_income": 50000, "marital_status": "married"})
    assert merged.gross_income == 50000
    assert merged.marital_status == MaritalStatus.married
    # Married convention mirrors create_tax_profile: both flags on.
    assert merged.claim_spouse_expense_exemption is True
    assert merged.claims_dependents_exemption is True
    breakdown = calculate_tax(merged)
    # 50000 - 9000 personal - 9000 family = 32000.
    assert breakdown.taxable_income == 32000


def test_merge_single_clears_spouse_allowance():
    base = TaxInput(gross_income=30000, claim_spouse_expense_exemption=True)
    merged = merge_tax_inputs(base, {"marital_status": "single"})
    assert merged.marital_status == MaritalStatus.single
    assert merged.claim_spouse_expense_exemption is False


def test_merge_without_base_uses_stated_only():
    merged = merge_tax_inputs(None, {"gross_income": 40000})
    assert merged.gross_income == 40000


# ── Contradiction detection ─────────────────────────────────────────────────


def _profile(**kw):
    base = dict(
        id=uuid.uuid4(),
        marital_status="single",
        num_dependents=0,
        disability_exemption_count=0,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_build_profile_updates_income_and_marital():
    income_id = uuid.uuid4()
    profile = _profile()
    income = [SimpleNamespace(id=income_id, type="salary", amount=20000.0, employer_name="Acme")]
    updates = build_profile_updates(
        {"gross_income": 50000, "marital_status": "married"}, profile, income, []
    )
    triples = {(u.entity, u.field, u.action) for u in updates}
    assert ("income_source", "amount", "update") in triples
    assert ("tax_profile", "marital_status", "update") in triples
    income_update = next(u for u in updates if u.entity == "income_source")
    assert income_update.entity_id == income_id
    assert income_update.new_value == 50000


def test_build_profile_updates_multiple_income_uses_choose():
    profile = _profile()
    income = [
        SimpleNamespace(id=uuid.uuid4(), type="salary", amount=12000.0, employer_name="A"),
        SimpleNamespace(id=uuid.uuid4(), type="rental", amount=8000.0, employer_name=None),
    ]
    updates = build_profile_updates({"gross_income": 50000}, profile, income, [])
    income_update = next(u for u in updates if u.entity == "income_source")
    assert income_update.action == "choose"
    assert len(income_update.options) == 2


def test_build_profile_updates_no_contradiction_is_empty():
    profile = _profile(marital_status="single", num_dependents=0)
    income = [SimpleNamespace(id=uuid.uuid4(), type="salary", amount=50000.0, employer_name="A")]
    updates = build_profile_updates(
        {"gross_income": 50000, "marital_status": "single"}, profile, income, []
    )
    assert updates == []


def test_build_profile_updates_new_deduction_creates():
    profile = _profile()
    updates = build_profile_updates(
        {"deductions": [{"category": "medical", "amount": 2000}]}, profile, [], []
    )
    deduction_update = next(u for u in updates if u.entity == "deduction")
    assert deduction_update.action == "create"
    assert deduction_update.category == "medical"
    assert deduction_update.new_value == 2000


# ── End-to-end through the chat endpoint ────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_carries_prior_income_and_married_into_calc(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """Replays the reported bug: 50,000 stated earlier must survive the 'married'
    follow-up, married must change the tax, and the contradiction with the stored
    20,000 profile must surface as an update offer."""

    def fake_llm(provider, user_message, model, system_prompt=None, max_tokens=None):
        if system_prompt == UNDERSTANDING_SYSTEM_PROMPT:
            return (
                '{"intent":"tax_calculation","stated":'
                '{"gross_income":50000,"marital_status":"married"},"reasoning":"what-if"}'
            )
        return "unused answer text"

    monkeypatch.setattr(qa, "_call_llm", fake_llm)
    monkeypatch.setattr("app.api.rag.provider_is_configured", lambda _provider: True)
    # Keep the deterministic calc path off ChromaDB.
    monkeypatch.setattr(qa, "retrieve_with_context", lambda *a, **k: ([], ""))

    token, _user = await _signup_and_login(client, username="merge-chat@example.com")
    profile = await _create_profile(client, token)  # single, 0 dependents
    await _add_income(client, token, profile["id"], amount=20000, employer_name="Acme")

    resp = await client.post(
        CHAT_URL,
        json={
            "question": "طيب اذا كنت متزوج؟",
            "provider": PROVIDER,
            "model": MODEL,
            "lang": "ar",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Prior-turn 50,000 carried forward (not the stored 20,000).
    assert data["tax_breakdown"]["gross_income"] == 50000
    # Married applied the family exemption: 50000 - 9000 - 9000 = 32000.
    assert data["tax_breakdown"]["taxable_income"] == 32000
    # Contradiction with the stored profile is offered for confirm-and-write.
    fields = {(u["entity"], u["field"]) for u in data["profile_updates"]}
    assert ("income_source", "amount") in fields
    assert ("tax_profile", "marital_status") in fields
    assert data["profile_id"] == profile["id"]


@pytest.mark.asyncio
async def test_chat_apply_update_writes_through_to_profile(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """The confirm card's apply endpoint writes the stated income to the profile."""

    def fake_llm(provider, user_message, model, system_prompt=None, max_tokens=None):
        if system_prompt == UNDERSTANDING_SYSTEM_PROMPT:
            return '{"intent":"tax_calculation","stated":{"gross_income":50000},"reasoning":"x"}'
        return "unused"

    monkeypatch.setattr(qa, "_call_llm", fake_llm)
    monkeypatch.setattr(qa, "retrieve_with_context", lambda *a, **k: ([], ""))

    monkeypatch.setattr("app.api.rag.provider_is_configured", lambda _provider: True)

    token, _user = await _signup_and_login(client, username="apply-chat@example.com")
    profile = await _create_profile(client, token)
    income = await _add_income(client, token, profile["id"], amount=20000)

    resp = await client.post(
        CHAT_URL,
        json={"question": "دخلي 50 ألف", "provider": PROVIDER, "model": MODEL, "lang": "ar"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    suggestion = next(
        u for u in resp.json()["profile_updates"] if u["entity"] == "income_source"
    )

    applied = await client.post(
        f"/api/v1/tax-profiles/{profile['id']}/apply-chat-update",
        json={
            "entity": "income_source",
            "field": "amount",
            "action": "update",
            "new_value": suggestion["new_value"],
            "entity_id": suggestion["entity_id"],
        },
        headers=_auth(token),
    )
    assert applied.status_code == 200, applied.text

    # The stored income source now reflects the chat-stated value.
    listed = await client.get(
        f"/api/v1/income-sources/?tax_profile_id={profile['id']}", headers=_auth(token)
    )
    assert listed.status_code == 200, listed.text
    amounts = {float(row["amount"]) for row in listed.json()}
    assert 50000 in amounts
    assert 20000 not in amounts
    _ = income  # original row was updated in place
