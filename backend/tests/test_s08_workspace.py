"""Year isolation, preview/save history, and optimistic profile writes."""

import hashlib
import json

import pytest


@pytest.mark.asyncio
async def test_workspace_year_isolation_saved_history_and_staleness(client):
    signup = await client.post("/api/v1/auth/signup", json={
        "username": "s08@example.com", "password": "StrongPass123!", "name": "S08",
    })
    assert signup.status_code == 201, signup.text
    login = await client.post("/api/v1/auth/login", json={
        "username": "s08@example.com", "password": "StrongPass123!",
    })
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    async def profile(year):
        response = await client.post("/api/v1/tax-profiles/", json={
            "user_id": "00000000-0000-0000-0000-000000000000",
            "tax_year": year, "marital_status": "single",
        }, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    a, b = await profile(2025), await profile(2026)
    for item, amount in [(a, "18000.001"), (b, "30000.002")]:
        response = await client.post("/api/v1/income-sources/", json={
            "tax_profile_id": item["id"], "type": "salary", "amount": amount,
        }, headers=headers)
        assert response.status_code == 201, response.text

    base = "/api/v1/tax-workspace/2025"
    before = await client.get(base, headers=headers)
    assert before.status_code == 200, before.text
    assert before.json()["preview"]["gross_income"] == "18000.001"
    assert before.json()["latest_run"] is None
    assert (await client.get(base + "/runs", headers=headers)).json() == []
    other = await client.get("/api/v1/tax-workspace/2026", headers=headers)
    assert other.json()["preview"]["gross_income"] == "30000.002"

    version = before.json()["profile_version"]
    saved = await client.post(base + "/runs", json={"expected_version": version}, headers=headers)
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["output_snapshot"] == before.json()["preview"]
    assert body["ruleset_id"] == "bayyan-demo-legacy-v1"
    assert body["input_snapshot"]["profile"]["tax_year"] == 2025
    assert body["input_snapshot"]["income_sources"][0]["amount"] == "18000.001"
    encoded = json.dumps(body["input_snapshot"], sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert body["input_fingerprint"] == hashlib.sha256(encoded.encode()).hexdigest()
    assert body["stale"] is False

    stale_write = await client.put(f"/api/v1/tax-profiles/{a['id']}", json={"num_dependents": 1},
                                   headers={**headers, "If-Match": str(version - 1)})
    assert stale_write.status_code == 409
    updated = await client.put(f"/api/v1/tax-profiles/{a['id']}", json={"num_dependents": 1},
                               headers={**headers, "If-Match": str(version)})
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == version + 1
    assert (await client.post(base + "/runs", json={"expected_version": version}, headers=headers)).status_code == 409
    after = await client.get(base, headers=headers)
    assert after.json()["latest_run"]["stale"] is True
    assert after.json()["preview"]["gross_income"] == "18000.001"

    second = await client.post(base + "/runs", json={"expected_version": version + 1}, headers=headers)
    assert second.status_code == 201, second.text
    history = (await client.get(base + "/runs", headers=headers)).json()
    assert len(history) == 2
    assert {row["id"] for row in history} == {body["id"], second.json()["id"]}
    assert history[0]["stale"] is False
    assert history[1]["stale"] is True
    assert history[1]["output_snapshot"] == body["output_snapshot"]


@pytest.mark.asyncio
async def test_workspace_requires_owner_and_supported_demo_year(client):
    for username in ["s08a@example.com", "s08b@example.com"]:
        await client.post("/api/v1/auth/signup", json={
            "username": username, "password": "StrongPass123!", "name": username,
        })
    async def auth(username):
        login = await client.post("/api/v1/auth/login", json={
            "username": username, "password": "StrongPass123!",
        })
        return {"Authorization": f"Bearer {login.json()['access_token']}"}
    owner, other = await auth("s08a@example.com"), await auth("s08b@example.com")
    profile = await client.post("/api/v1/tax-profiles/", json={
        "user_id": "00000000-0000-0000-0000-000000000000",
        "tax_year": 2027, "marital_status": "single",
    }, headers=owner)
    assert profile.status_code == 201
    assert (await client.get("/api/v1/tax-workspace/2027", headers=owner)).status_code == 422
    assert (await client.post("/api/v1/tax-workspace/2027/runs", json={"expected_version": 1}, headers=owner)).status_code == 422
    assert (await client.get("/api/v1/tax-workspace/2027/runs", headers=owner)).json() == []
    assert (await client.get("/api/v1/tax-workspace/2027", headers=other)).status_code == 404
