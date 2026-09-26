import pytest
from httpx import AsyncClient


SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
TAX_PROFILES_URL = "/api/v1/tax-profiles/"
INCOME_SOURCES_URL = "/api/v1/income-sources/"
DEDUCTIONS_URL = "/api/v1/deductions/"


USER_A = {
    "username": "tax-profile-a@example.com",
    "password": "StrongPass123!",
    "name": "Tax Profile A",
}
USER_B = {
    "username": "tax-profile-b@example.com",
    "password": "StrongPass123!",
    "name": "Tax Profile B",
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
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2026,
        "marital_status": "married",
        "num_dependents": 2,
    }
    payload.update(overrides)
    resp = await client.post(TAX_PROFILES_URL, json=payload, headers=_auth(token))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_tax_profile_jordan_fields_income_withholding_and_deductions(
    client: AsyncClient,
):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)

    assert profile["claims_dependents_exemption"] is True
    assert profile["claim_spouse_expense_exemption"] is True
    assert profile["residency_status"] == "resident"

    updated_profile = await client.put(
        f"{TAX_PROFILES_URL}{profile['id']}",
        json={
            "disability_exemption_count": 1,
            "filing_status": "joint",
        },
        headers=_auth(token),
    )
    assert updated_profile.status_code == 200, updated_profile.text
    assert updated_profile.json()["disability_exemption_count"] == 1

    income_resp = await client.post(
        INCOME_SOURCES_URL,
        json={
            "tax_profile_id": profile["id"],
            "type": "salary",
            "amount": "40000",
            "tax_withheld": "1500",
            "employer_name": "Acme",
        },
        headers=_auth(token),
    )
    assert income_resp.status_code == 201, income_resp.text
    income = income_resp.json()
    assert income["tax_withheld"] == "1500.00"

    updated_income = await client.put(
        f"{INCOME_SOURCES_URL}{income['id']}",
        json={"amount": "42000", "tax_withheld": "1700"},
        headers=_auth(token),
    )
    assert updated_income.status_code == 200, updated_income.text
    assert updated_income.json()["tax_withheld"] == "1700.00"

    deduction_resp = await client.post(
        DEDUCTIONS_URL,
        json={
            "tax_profile_id": profile["id"],
            "category": "rent",
            "amount": "3000",
        },
        headers=_auth(token),
    )
    assert deduction_resp.status_code == 201, deduction_resp.text
    deduction = deduction_resp.json()

    updated_deduction = await client.put(
        f"{DEDUCTIONS_URL}{deduction['id']}",
        json={"category": "housing_murabaha", "amount": "2500"},
        headers=_auth(token),
    )
    assert updated_deduction.status_code == 200, updated_deduction.text
    assert updated_deduction.json()["category"] == "housing_murabaha"

    calc_resp = await client.post(
        f"/api/v1/tax-calculations/{profile['id']}/calculate",
        headers=_auth(token),
    )
    assert calc_resp.status_code == 200, calc_resp.text
    calc = calc_resp.json()
    assert calc["disability_exemption"] == 2000
    assert calc["expense_exemption"] == 2500
    assert calc["total_tax_withheld"] == 1700
    assert "net_tax_due" in calc


@pytest.mark.asyncio
async def test_deduction_beneficiary_roundtrip_and_tax_invariance(client: AsyncClient):
    user = {
        "username": "beneficiary-test@example.com",
        "password": "StrongPass123!",
        "name": "Beneficiary Test",
    }
    token = await _signup_and_login(client, user)
    profile = await _create_profile(client, token)

    await client.post(
        INCOME_SOURCES_URL,
        json={"tax_profile_id": profile["id"], "type": "salary", "amount": "40000"},
        headers=_auth(token),
    )

    # medical deduction WITHOUT a beneficiary
    created = await client.post(
        DEDUCTIONS_URL,
        json={"tax_profile_id": profile["id"], "category": "medical", "amount": "800"},
        headers=_auth(token),
    )
    assert created.status_code == 201, created.text
    ded = created.json()
    assert ded["beneficiary"] is None
    assert ded["beneficiary_name"] is None

    calc_before = await client.post(
        f"/api/v1/tax-calculations/{profile['id']}/calculate", headers=_auth(token)
    )
    tax_before = calc_before.json()["tax_liability"]

    # tag it for a child — partial update leaves category/amount untouched
    updated = await client.put(
        f"{DEDUCTIONS_URL}{ded['id']}",
        json={"beneficiary": "child", "beneficiary_name": "Mohannad"},
        headers=_auth(token),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["beneficiary"] == "child"
    assert body["beneficiary_name"] == "Mohannad"
    assert body["category"] == "medical"
    assert body["amount"] == "800.00"

    # round-trip via GET
    fetched = await client.get(f"{DEDUCTIONS_URL}{ded['id']}", headers=_auth(token))
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["beneficiary"] == "child"
    assert fetched.json()["beneficiary_name"] == "Mohannad"

    # the beneficiary tag is invisible to the tax engine (pooled by category)
    calc_after = await client.post(
        f"/api/v1/tax-calculations/{profile['id']}/calculate", headers=_auth(token)
    )
    assert calc_after.json()["tax_liability"] == tax_before

    # invalid beneficiary value is rejected by the Literal
    bad = await client.post(
        DEDUCTIONS_URL,
        json={
            "tax_profile_id": profile["id"],
            "category": "medical",
            "amount": "100",
            "beneficiary": "cousin",
        },
        headers=_auth(token),
    )
    assert bad.status_code == 422, bad.text


@pytest.mark.asyncio
async def test_negative_values_are_rejected(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token)

    bad_profile = await client.put(
        f"{TAX_PROFILES_URL}{profile['id']}",
        json={"num_dependents": -1},
        headers=_auth(token),
    )
    assert bad_profile.status_code == 422

    bad_income = await client.post(
        INCOME_SOURCES_URL,
        json={
            "tax_profile_id": profile["id"],
            "type": "salary",
            "amount": "-1",
        },
        headers=_auth(token),
    )
    assert bad_income.status_code == 422

    bad_deduction = await client.post(
        DEDUCTIONS_URL,
        json={
            "tax_profile_id": profile["id"],
            "category": "rent",
            "amount": "-1",
        },
        headers=_auth(token),
    )
    assert bad_deduction.status_code == 422


@pytest.mark.asyncio
async def test_other_user_cannot_update_tax_profile_children(client: AsyncClient):
    token_a = await _signup_and_login(client, USER_A)
    profile = await _create_profile(client, token_a)
    income = (
        await client.post(
            INCOME_SOURCES_URL,
            json={
                "tax_profile_id": profile["id"],
                "type": "salary",
                "amount": "20000",
            },
            headers=_auth(token_a),
        )
    ).json()
    deduction = (
        await client.post(
            DEDUCTIONS_URL,
            json={
                "tax_profile_id": profile["id"],
                "category": "medical",
                "amount": "500",
            },
            headers=_auth(token_a),
        )
    ).json()

    token_b = await _signup_and_login(client, USER_B)

    profile_resp = await client.put(
        f"{TAX_PROFILES_URL}{profile['id']}",
        json={"num_dependents": 0},
        headers=_auth(token_b),
    )
    income_resp = await client.put(
        f"{INCOME_SOURCES_URL}{income['id']}",
        json={"amount": "1"},
        headers=_auth(token_b),
    )
    deduction_resp = await client.put(
        f"{DEDUCTIONS_URL}{deduction['id']}",
        json={"amount": "1"},
        headers=_auth(token_b),
    )

    assert profile_resp.status_code == 404
    assert income_resp.status_code == 404
    assert deduction_resp.status_code == 404
