"""Exact financial arithmetic and explicit demo-year selection."""

from decimal import Decimal

import pytest

from app.models import DeductionCategory
from app.tax_engine import TaxInput, calculate_tax
from app.tax_engine.decimal_engine import DEMO_RULESET_ID, calculate_decimal


@pytest.mark.parametrize("gross", [
    "0", "9000", "18000", "23000", "25000", "28000", "33000", "50000", "250000",
])
def test_decimal_matches_recorded_whole_dinar_baseline(gross):
    old = calculate_tax(TaxInput(gross_income=gross))
    new = calculate_decimal(TaxInput(gross_income=gross), tax_year=2026).to_payload()
    assert new["taxable_income"] == f"{old.taxable_income:.3f}"
    assert new["tax_liability"] == f"{old.tax_liability:.3f}"
    assert new["ruleset_id"] == DEMO_RULESET_ID
    assert new["official_filing"] is False


def test_fractional_donation_and_withholding_match_legacy_at_fils_precision():
    data = TaxInput(
        gross_income=Decimal("50000.125"), tax_withheld=Decimal("500.333"),
        deductions={DeductionCategory.MEDICAL: Decimal("123.456"), DeductionCategory.DONATIONS: Decimal("456.789")},
    )
    result = calculate_decimal(data, tax_year=2025).to_payload()
    assert result["taxable_income"] == "40419.880"
    assert result["tax_liability"] == "7604.970"
    assert result["net_tax_due"] == "7104.637"
    assert result["deductions_allowed"]["medical"] == "123.456"


def test_refund_and_bracket_boundary():
    result = calculate_decimal(TaxInput(gross_income=Decimal("14000"), tax_withheld=Decimal("300.123")), tax_year=2026)
    assert result.to_payload()["tax_liability"] == "250.000"
    assert result.to_payload()["refund_due"] == "50.123"
    assert result.to_payload()["bracket_breakdown"][0]["to"] == "5000.000"


def test_exact_half_even_removes_float_tie_artifact():
    data = TaxInput(gross_income=Decimal("9000.010"))
    assert f"{calculate_tax(data).tax_liability:.3f}" == "0.001"
    assert calculate_decimal(data, tax_year=2026).to_payload()["tax_liability"] == "0.000"


def test_nonresident_and_unknown_category_behavior():
    nonresident = calculate_decimal(TaxInput(
        gross_income=Decimal("20000"), residency_status="nonresident_other",
    ), tax_year=2026)
    assert nonresident.personal_exemption == 0
    with pytest.raises(ValueError):
        calculate_decimal(TaxInput(
            gross_income=Decimal("20000"), deductions={"unknown": Decimal("1")},
        ), tax_year=2026)


@pytest.mark.parametrize("gross", ["NaN", "Infinity", "-1", "abc", 1.2, "1.2345", "1000000000000"])
def test_invalid_money_is_rejected(gross):
    with pytest.raises(ValueError):
        calculate_decimal(TaxInput(gross_income=gross), tax_year=2026)


def test_unsupported_year_is_rejected():
    with pytest.raises(ValueError, match="No demonstration ruleset"):
        calculate_decimal(TaxInput(gross_income=Decimal("1")), tax_year=2027)


@pytest.mark.asyncio
async def test_v2_api_returns_money_strings_without_changing_legacy(client):
    signup = await client.post("/api/v1/auth/signup", json={
        "username": "s07@example.com", "password": "StrongPass123!", "name": "S07",
    })
    assert signup.status_code == 201
    login = await client.post("/api/v1/auth/login", json={
        "username": "s07@example.com", "password": "StrongPass123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = await client.post("/api/v1/tax-profiles/", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2026, "marital_status": "single",
    }, headers=headers)
    assert profile.status_code == 201, profile.text
    profile_id = profile.json()["id"]
    income = await client.post("/api/v1/income-sources/", json={
        "tax_profile_id": profile_id, "type": "salary",
        "amount": "18000.001", "tax_withheld": "700.00",
    }, headers=headers)
    assert income.status_code == 201, income.text
    assert income.json()["amount"] == "18000.001"
    overprecise = await client.post("/api/v1/income-sources/", json={
        "tax_profile_id": profile_id, "type": "salary", "amount": "1.2345",
    }, headers=headers)
    assert overprecise.status_code == 422

    legacy = await client.post(f"/api/v1/tax-calculations/{profile_id}/calculate", headers=headers)
    new = await client.post(f"/api/v1/tax-calculations/{profile_id}/calculate-v2", headers=headers)
    assert legacy.status_code == new.status_code == 200, new.text
    assert legacy.json()["tax_liability"] == 650.0
    assert new.json()["tax_liability"] == "650.000"
    assert new.json()["gross_income"] == "18000.001"
    assert new.json()["refund_due"] == "50.000"
    assert new.json()["official_filing"] is False
    assert new.json()["ruleset_id"] == DEMO_RULESET_ID
    assert isinstance(new.json()["bracket_breakdown"][0]["income"], str)


@pytest.mark.asyncio
async def test_v2_api_rejects_unconfigured_demo_year(client):
    await client.post("/api/v1/auth/signup", json={
        "username": "s07year@example.com", "password": "StrongPass123!", "name": "S07 Year",
    })
    login = await client.post("/api/v1/auth/login", json={
        "username": "s07year@example.com", "password": "StrongPass123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = await client.post("/api/v1/tax-profiles/", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2027, "marital_status": "single",
    }, headers=headers)
    assert profile.status_code == 201, profile.text
    response = await client.post(f"/api/v1/tax-calculations/{profile.json()['id']}/calculate-v2", headers=headers)
    assert response.status_code == 422
