"""GET /api/v1/users/me/usage smoke test.

The self-serve POST /me/tier route is gone — tier changes are admin-only now
(see test_admin.py once it exists, plus PATCH /admin/users/{id}). The usage
endpoint itself is unaffected and still reflects whatever tier the user is on.
"""
import pytest
from httpx import AsyncClient


SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
USAGE_URL = "/api/v1/users/me/usage"

USER_A = {
    "username": "tier-user@example.com",
    "password": "StrongPass123!",
    "name": "Tier User",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signup_and_login(client: AsyncClient, user: dict) -> str:
    await client.post(SIGNUP_URL, json=user)
    resp = await client.post(
        LOGIN_URL, json={"username": user["username"], "password": user["password"]}
    )
    return resp.json()["access_token"]


@pytest.mark.asyncio
async def test_usage_endpoint_returns_current_tier_limits(client: AsyncClient):
    token = await _signup_and_login(client, USER_A)

    resp = await client.get(USAGE_URL, headers=_auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tier"] == "Basic"
    assert body["messages"] == {"used": 0, "limit": 60, "remaining": 60}
    assert body["docs"] == {"used": 0, "limit": 10, "remaining": 10}
    assert body["max_tokens"] == 1024
    assert body["allowed_models"] == [
        {"provider": "groq", "model": "llama-3.1-8b-instant"},
        {"provider": "gemini", "model": "gemini-2.5-flash"},
    ]
