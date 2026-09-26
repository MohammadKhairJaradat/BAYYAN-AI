"""Run with S05_POSTGRES_URL against an isolated migrated PostgreSQL database."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import usage as usage_service
from app.models.database import UsageReservation, User


@pytest.mark.asyncio
async def test_twenty_concurrent_requests_reserve_only_one_provider_attempt(monkeypatch):
    url = os.environ.get("S05_POSTGRES_URL")
    if not url:
        pytest.skip("Set S05_POSTGRES_URL to an isolated migrated PostgreSQL database")

    engine = create_async_engine(url, pool_size=20, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(usage_service, "operation_limit", lambda _tier, _operation: 1)
    try:
        async with sessions() as db:
            user = User(username=f"s05-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S05")
            db.add(user)
            await db.commit()
            user_id = user.id

        provider_calls = 0

        async def attempt(n: int) -> int:
            nonlocal provider_calls
            async with sessions() as db:
                try:
                    reservation_id = await usage_service.reserve_usage(
                        db, user_id=user_id, tier="Basic", operation="advisor",
                        idempotency_key=f"request-{n}",
                    )
                except HTTPException as exc:
                    await db.rollback()
                    return exc.status_code
                provider_calls += 1
                await usage_service.settle_usage(db, reservation_id)
                return 200

        results = await asyncio.gather(*(attempt(n) for n in range(20)))
        assert results.count(200) == provider_calls == 1
        assert results.count(429) == 19

        winner = results.index(200)
        async with sessions() as db:
            with pytest.raises(HTTPException) as replay:
                await usage_service.reserve_usage(
                    db, user_id=user_id, tier="Basic", operation="advisor",
                    idempotency_key=f"request-{winner}",
                )
            assert replay.value.status_code == 409
            assert await db.scalar(select(func.count()).select_from(UsageReservation).where(
                UsageReservation.user_id == user_id,
            )) == 1
    finally:
        await engine.dispose()
