"""Run with S04_POSTGRES_URL against an isolated migrated PostgreSQL database."""

import asyncio
import os
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main import app
from app.models.connection import get_db


@pytest.mark.asyncio
async def test_postgres_concurrent_refresh_allows_one_rotation():
    url = os.environ.get("S04_POSTGRES_URL")
    if not url:
        pytest.skip("Set S04_POSTGRES_URL to an isolated migrated PostgreSQL database")
    engine = create_async_engine(url, pool_size=3)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def postgres_db():
        async with sessions() as db:
            yield db

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = postgres_db
    try:
        username = f"s04-{uuid.uuid4().hex}@example.com"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            signup = await client.post("/api/v1/auth/signup", json={
                "username": username, "password": "StrongPass123!", "name": "S04",
            })
            assert signup.status_code == 201, signup.text
            login = await client.post("/api/v1/auth/login", json={
                "username": username, "password": "StrongPass123!",
            })
            assert login.status_code == 200, login.text
            old_cookie = login.cookies.get("bayyan_refresh")
            assert old_cookie

            async def rotate():
                async with AsyncClient(transport=transport, base_url="http://test") as attempt:
                    response = await attempt.post("/api/v1/auth/refresh", headers={
                        "Origin": "http://localhost:5173",
                        "Cookie": f"bayyan_refresh={old_cookie}",
                    })
                    return response

            first, second = await asyncio.gather(rotate(), rotate())
            assert sorted([first.status_code, second.status_code]) == [200, 401]
            winner = first if first.status_code == 200 else second
            access = winner.json()["access_token"]
            new_cookie = winner.cookies.get("bayyan_refresh")
            assert new_cookie != old_cookie
            me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
            assert me.status_code == 200, me.text
            logout = await client.post("/api/v1/auth/logout", headers={
                "Origin": "http://localhost:5173", "Cookie": f"bayyan_refresh={new_cookie}",
            })
            assert logout.status_code == 204
            after_logout = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
            assert after_logout.status_code == 401
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        await engine.dispose()
