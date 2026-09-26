import pytest
from pydantic import ValidationError
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import SecurityAuditEvent, User
from app.config import Settings

SIGNUP_URL = "/api/v1/auth/signup"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL = "/api/v1/auth/me"

TEST_USER = {
    "username": "testuser",
    "password": "StrongPass123!",
    "name": "Test User",
}


def test_production_rejects_default_secret_and_http_origin():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", FRONTEND_ORIGIN="https://example.com", SECRET_KEY="change-me-to-a-random-secret")
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", FRONTEND_ORIGIN="http://example.com", SECRET_KEY="x" * 40)


async def _signup(client: AsyncClient, **overrides) -> dict:
    payload = {**TEST_USER, **overrides}
    resp = await client.post(SIGNUP_URL, json=payload)
    return resp


async def _login(client: AsyncClient, username: str = TEST_USER["username"], password: str = TEST_USER["password"]) -> dict:
    resp = await client.post(LOGIN_URL, json={"username": username, "password": password})
    return resp


# ── Signup ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_creates_user(client: AsyncClient):
    resp = await _signup(client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == TEST_USER["username"]
    assert data["name"] == TEST_USER["name"]
    assert data["is_active"] is True
    assert "hashed_password" not in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_signup_duplicate_username_fails(client: AsyncClient):
    await _signup(client)
    resp = await _signup(client)
    assert resp.status_code == 400
    assert "already taken" in resp.json()["detail"].lower()


# ── Login ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_correct_credentials(client: AsyncClient):
    await _signup(client)
    resp = await _login(client)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert resp.cookies.get("bayyan_refresh")
    assert "httponly" in resp.headers["set-cookie"].lower()
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await _signup(client)
    resp = await _login(client, password="WrongPassword!")
    assert resp.status_code == 401


# ── Protected Endpoints ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    resp = await client.get(ME_URL)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_with_valid_token(client: AsyncClient):
    await _signup(client)
    login_resp = await _login(client)
    token = login_resp.json()["access_token"]

    resp = await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == TEST_USER["username"]
    assert data["name"] == TEST_USER["name"]


# ── Refresh ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_flow(client: AsyncClient):
    await _signup(client)
    login_resp = await _login(client)
    old_cookie = login_resp.cookies.get("bayyan_refresh")

    resp = await client.post(REFRESH_URL, headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" not in data
    assert resp.cookies.get("bayyan_refresh") != old_cookie

    # New access token should work
    new_token = data["access_token"]
    me_resp = await client.get(ME_URL, headers={"Authorization": f"Bearer {new_token}"})
    assert me_resp.status_code == 200

    replay = await client.post(REFRESH_URL, headers={
        "Origin": "http://localhost:5173", "Cookie": f"bayyan_refresh={old_cookie}",
    })
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh(client: AsyncClient, db_session: AsyncSession):
    await _signup(client)
    login_resp = await _login(client)
    token = login_resp.json()["access_token"]
    old_cookie = login_resp.cookies.get("bayyan_refresh")
    logout = await client.post("/api/v1/auth/logout", headers={"Origin": "http://localhost:5173"})
    assert logout.status_code == 204
    assert (await client.get(ME_URL, headers={"Authorization": f"Bearer {token}"})).status_code == 401
    assert (await client.post(REFRESH_URL, headers={
        "Origin": "http://localhost:5173", "Cookie": f"bayyan_refresh={old_cookie}",
    })).status_code == 401
    actions = (await db_session.execute(select(SecurityAuditEvent.action))).scalars().all()
    assert actions == ["auth.login", "auth.logout"]


@pytest.mark.asyncio
async def test_refresh_rejects_foreign_origin(client: AsyncClient):
    await _signup(client)
    await _login(client)
    response = await client.post(REFRESH_URL, headers={"Origin": "https://attacker.example"})
    assert response.status_code == 403
    login = await client.post(LOGIN_URL, json={
        "username": TEST_USER["username"], "password": TEST_USER["password"],
    }, headers={"Origin": "https://attacker.example"})
    assert login.status_code == 403


@pytest.mark.asyncio
async def test_inactive_user_cannot_login_or_refresh(client: AsyncClient, db_session: AsyncSession):
    await _signup(client)
    await _login(client)
    user = (await db_session.execute(select(User).where(User.username == TEST_USER["username"]))).scalar_one()
    user.is_active = False
    await db_session.commit()
    assert (await _login(client)).status_code == 401
    assert (await client.post(REFRESH_URL, headers={"Origin": "http://localhost:5173"})).status_code == 401


@pytest.mark.asyncio
async def test_signup_admin_name_does_not_promote(client: AsyncClient):
    response = await _signup(client, username="admin")
    assert response.status_code == 201
    assert response.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_explicit_admin_bootstrap_is_audited(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    from app.auth import bootstrap_admin
    from tests.conftest import TestSessionFactory

    await _signup(client, username="chosen-admin")
    monkeypatch.setattr(bootstrap_admin, "async_session_factory", TestSessionFactory)
    assert await bootstrap_admin.bootstrap("chosen-admin") is True
    assert await bootstrap_admin.bootstrap("chosen-admin") is False
    user = (await db_session.execute(select(User).where(User.username == "chosen-admin"))).scalar_one()
    assert user.is_admin is True
    actions = (await db_session.execute(select(SecurityAuditEvent.action))).scalars().all()
    assert actions == ["admin.bootstrap"]
