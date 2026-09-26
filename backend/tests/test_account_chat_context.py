from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.models import DeductionCategory
from app.models.database import (
    AdvisorReportSnapshot,
    IncomeSource,
    TaxProfile,
    User,
)
from app.rag import account_context
from app.rag import qa
from app.tax_engine import TaxInput

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
TAX_PROFILES_URL = "/api/v1/tax-profiles/"
INCOME_SOURCES_URL = "/api/v1/income-sources/"
CHAT_URL = "/api/v1/rag/chat"
PROVIDER = "gemini"
MODEL = "gemini-2.5-flash"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(
    client: AsyncClient,
    *,
    username: str = "account-chat@example.com",
) -> tuple[str, dict]:
    user = {
        "username": username,
        "password": "StrongPass123!",
        "name": "Account Chat",
    }
    signup = await client.post(SIGNUP_URL, json=user)
    assert signup.status_code == 201, signup.text
    login = await client.post(
        LOGIN_URL,
        json={"username": user["username"], "password": user["password"]},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"], signup.json()


async def _create_profile(
    client: AsyncClient,
    token: str,
    *,
    tax_year: int = 2026,
    marital_status: str = "single",
    num_dependents: int = 0,
) -> dict:
    resp = await client.post(
        TAX_PROFILES_URL,
        json={
            "user_id": "00000000-0000-0000-0000-000000000000",
            "tax_year": tax_year,
            "marital_status": marital_status,
            "num_dependents": num_dependents,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_income(
    client: AsyncClient,
    token: str,
    profile_id: str,
    *,
    amount: float = 20000.0,
    employer_name: str = "Acme",
) -> dict:
    resp = await client.post(
        INCOME_SOURCES_URL,
        json={
            "tax_profile_id": profile_id,
            "type": "salary",
            "amount": str(amount),
            "employer_name": employer_name,
        },
        headers=_auth(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _db_user(db_session, username: str) -> User:
    user = User(username=username, hashed_password="hashed", name=username)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def no_background_chat_tasks(monkeypatch: pytest.MonkeyPatch):
    async def noop_refresh(*_args, **_kwargs):
        return None

    async def noop_title(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.api.rag.refresh_session_memory", noop_refresh)
    monkeypatch.setattr("app.api.rag.generate_and_save_title", noop_title)
    monkeypatch.setattr("app.api.rag.provider_is_configured", lambda _provider: True)


@pytest.mark.asyncio
async def test_account_context_is_user_scoped(db_session):
    user_a = await _db_user(db_session, "scope-a@example.com")
    user_b = await _db_user(db_session, "scope-b@example.com")
    profile_a = TaxProfile(
        user_id=user_a.id,
        tax_year=2026,
        marital_status="single",
        num_dependents=0,
    )
    profile_b = TaxProfile(
        user_id=user_b.id,
        tax_year=2026,
        marital_status="single",
        num_dependents=0,
    )
    db_session.add_all([profile_a, profile_b])
    await db_session.flush()
    db_session.add_all(
        [
            IncomeSource(
                tax_profile_id=profile_a.id,
                type="salary",
                amount=20000,
                employer_name="User A Employer",
            ),
            IncomeSource(
                tax_profile_id=profile_b.id,
                type="salary",
                amount=90000,
                employer_name="User B Employer",
            ),
        ]
    )
    await db_session.commit()

    ctx = await account_context.build_account_chat_context(
        db_session,
        user_id=user_a.id,
        question="What is my salary?",
        current_year=2026,
    )

    assert ctx.context is not None
    assert "20000" in ctx.context
    assert "User A Employer" in ctx.context
    assert "90000" not in ctx.context
    assert "User B Employer" not in ctx.context


@pytest.mark.asyncio
async def test_account_context_uses_explicit_tax_year(db_session):
    user = await _db_user(db_session, "years@example.com")
    profile_2025 = TaxProfile(
        user_id=user.id,
        tax_year=2025,
        marital_status="single",
        num_dependents=0,
    )
    profile_2026 = TaxProfile(
        user_id=user.id,
        tax_year=2026,
        marital_status="single",
        num_dependents=0,
    )
    db_session.add_all([profile_2025, profile_2026])
    await db_session.flush()
    db_session.add_all(
        [
            IncomeSource(tax_profile_id=profile_2025.id, type="salary", amount=15000),
            IncomeSource(tax_profile_id=profile_2026.id, type="salary", amount=22000),
        ]
    )
    await db_session.commit()

    ctx = await account_context.build_account_chat_context(
        db_session,
        user_id=user.id,
        question="What was my salary in 2025?",
        current_year=2026,
    )

    assert ctx.selected_tax_year == 2025
    assert ctx.context is not None
    assert '"selected_tax_year": 2025' in ctx.context
    assert "15000" in ctx.context
    assert "22000" not in ctx.context


@pytest.mark.asyncio
async def test_account_context_prepares_tax_inputs_with_question_overrides(db_session):
    user = await _db_user(db_session, "override@example.com")
    profile = TaxProfile(
        user_id=user.id,
        tax_year=2026,
        marital_status="single",
        num_dependents=0,
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add(IncomeSource(tax_profile_id=profile.id, type="salary", amount=20000))
    await db_session.commit()

    ctx = await account_context.build_account_chat_context(
        db_session,
        user_id=user.id,
        question="What if I am married and salary is 30000 JOD?",
        current_year=2026,
    )

    assert ctx.tax_inputs is not None
    assert ctx.tax_inputs.gross_income == 30000
    assert ctx.tax_inputs.marital_status.value == "married"


def test_account_context_override_preserves_signed_decimal_amount():
    base = TaxInput(gross_income=20_000)

    result = account_context._apply_question_overrides(
        base,
        "What if salary is -500.75 JOD?",
    )

    assert result.gross_income == -500.75


def test_account_context_override_parses_thousand_amount_words():
    base = TaxInput(gross_income=20_000)

    result_en = account_context._apply_question_overrides(
        base,
        "What if salary is 50 thousand JOD?",
    )
    result_ar = account_context._apply_question_overrides(
        base,
        "\u0645\u0627\u0630\u0627 \u0644\u0648 "
        "\u0631\u0627\u062a\u0628\u064a 50 \u0627\u0644\u0641 "
        "\u062f\u064a\u0646\u0627\u0631\u061f",
    )

    assert result_en.gross_income == 50000
    assert result_ar.gross_income == 50000


@pytest.mark.parametrize(
    "question",
    [
        "What's my personal exemption this year?",
        "قدّيش إعفائي الشخصي هالسنة؟",
    ],
)
def test_account_context_treats_personal_exemption_questions_as_account_related(question):
    assert account_context.is_account_related_question(question)


def test_account_context_aggregates_duplicate_deduction_rows():
    profile = SimpleNamespace(
        marital_status="single",
        num_dependents=0,
        residency_status="resident",
        claims_dependents_exemption=False,
        claim_spouse_expense_exemption=False,
        disability_exemption_count=0,
    )
    income_rows = [SimpleNamespace(amount=20_000, tax_withheld=0)]
    deduction_rows = [
        SimpleNamespace(category="medical", amount=100),
        SimpleNamespace(category="medical", amount=50.75),
    ]

    inputs = account_context._tax_inputs_from_rows(profile, income_rows, deduction_rows)

    assert inputs.deductions[DeductionCategory.MEDICAL] == 150.75


@pytest.mark.asyncio
async def test_account_context_marks_latest_advisor_report_stale(db_session):
    user = await _db_user(db_session, "advisor-source@example.com")
    profile = TaxProfile(
        user_id=user.id,
        tax_year=2026,
        marital_status="single",
        num_dependents=0,
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add(IncomeSource(tax_profile_id=profile.id, type="salary", amount=20000))
    db_session.add(
        AdvisorReportSnapshot(
            user_id=user.id,
            tax_profile_id=profile.id,
            lang="en",
            report={
                "tax_profile_id": str(profile.id),
                "lang": "en",
                "status": "complete",
                "missing_fields": [],
                "baseline": None,
                "scenarios": [],
                "deduction_opportunities": [],
                "risk_flags": [],
                "action_plan": [],
                "narratives": {},
                "errors": [],
            },
            input_fingerprint="stale-fingerprint",
        )
    )
    await db_session.commit()

    ctx = await account_context.build_account_chat_context(
        db_session,
        user_id=user.id,
        question="What does my advisor report say?",
        current_year=2026,
    )

    advisor_sources = [source for source in ctx.sources if source["kind"] == "advisor_report"]
    assert advisor_sources
    assert advisor_sources[0]["stale"] is True
    assert "latest_advisor_report" in (ctx.context or "")


@pytest.mark.asyncio
async def test_chat_account_tax_question_uses_tax_engine(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    no_background_chat_tasks,
):
    def no_sources(*_args, **_kwargs):
        return [], ""

    def fail_llm(*_args, **_kwargs):
        raise AssertionError("account tax calculation must not call the chat LLM")

    monkeypatch.setattr(qa, "retrieve_with_context", no_sources)
    monkeypatch.setattr(qa, "_call_llm", fail_llm)

    token, _user = await _signup_and_login(client, username="tax-engine-chat@example.com")
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=20000)

    resp = await client.post(
        CHAT_URL,
        json={
            "question": "How much tax do I owe?",
            "provider": PROVIDER,
            "model": MODEL,
            "lang": "en",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["provider"] == "tax_engine"
    assert data["tax_breakdown"]["gross_income"] == 20000
    assert any(source["kind"] == "account_profile" for source in data["sources"])


@pytest.mark.asyncio
async def test_chat_account_recall_sends_saved_profile_context_to_llm(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    no_background_chat_tasks,
):
    calls: list[dict] = []

    def fail_retrieve(*_args, **_kwargs):
        raise AssertionError("account recall should not call law retrieval")

    def fake_llm(provider, user_message, model, system_prompt, max_tokens=None):
        calls.append(
            {
                "provider": provider,
                "user_message": user_message,
                "model": model,
                "system_prompt": system_prompt,
                "max_tokens": max_tokens,
            }
        )
        return "Your saved salary is 20,000 JOD."

    monkeypatch.setattr(qa, "retrieve_with_context", fail_retrieve)
    monkeypatch.setattr(qa, "_call_llm", fake_llm)

    token, _user = await _signup_and_login(client, username="recall-chat@example.com")
    profile = await _create_profile(client, token)
    await _add_income(client, token, profile["id"], amount=20000, employer_name="Acme")

    resp = await client.post(
        CHAT_URL,
        json={
            "question": "What is my salary?",
            "provider": PROVIDER,
            "model": MODEL,
            "lang": "en",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["answer"] == "Your saved salary is 20,000 JOD."
    assert calls
    # The first _call_llm is now the understanding/router call; the account context
    # is injected into the answer call. Find it regardless of ordering.
    answer_call = next(
        c for c in calls if "Authenticated account context" in c["user_message"]
    )
    assert "20000" in answer_call["user_message"]
    assert "Acme" in answer_call["user_message"]
    assert any(source["kind"] == "account_profile" for source in data["sources"])
