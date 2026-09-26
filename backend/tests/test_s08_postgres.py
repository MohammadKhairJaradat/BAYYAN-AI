"""Run with S08_POSTGRES_URL against an isolated database migrated through 022."""

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.database import TaxProfile, User
from app.services.profile_version import bump_profile_version, lock_profile_version


@pytest.mark.asyncio
async def test_profile_version_lock_rejects_concurrent_stale_writer():
    url = os.environ.get("S08_POSTGRES_URL")
    if not url:
        pytest.skip("Set S08_POSTGRES_URL to an isolated migrated PostgreSQL database")
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = None
    try:
        async with sessions() as db:
            column = (await db.execute(text("""
                SELECT column_default FROM information_schema.columns
                WHERE table_name = 'tax_profiles' AND column_name = 'version'
            """))).scalar_one()
            assert column == "1"
            table = (await db.execute(text("SELECT to_regclass('calculation_runs')"))).scalar_one()
            assert table == "calculation_runs"
            user = User(username=f"s08-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S08")
            db.add(user)
            await db.flush()
            user_id = user.id
            profile = TaxProfile(user_id=user.id, tax_year=2026, marital_status="single")
            db.add(profile)
            await db.commit()
            profile_id = profile.id

        acquired = asyncio.Event()
        read_old = asyncio.Event()
        release = asyncio.Event()

        async def first_writer():
            async with sessions() as db:
                await lock_profile_version(db, profile_id, 1)
                acquired.set()
                await release.wait()
                await bump_profile_version(db, profile_id)
                await db.commit()

        async def second_writer():
            async with sessions() as db:
                await acquired.wait()
                # Reproduce the normal route's ownership read before the lock.
                assert (await db.get(TaxProfile, profile_id)).version == 1
                read_old.set()
                try:
                    await lock_profile_version(db, profile_id, 1)
                except HTTPException as exc:
                    assert exc.status_code == 409
                    return
                pytest.fail("Concurrent stale writer was allowed")

        first = asyncio.create_task(first_writer())
        second = asyncio.create_task(second_writer())
        try:
            await asyncio.wait_for(read_old.wait(), timeout=5)
            release.set()
            await asyncio.wait_for(asyncio.gather(first, second), timeout=10)
        finally:
            release.set()
        async with sessions() as db:
            assert (await db.get(TaxProfile, profile_id)).version == 2
    finally:
        if user_id:
            async with sessions() as db:
                await db.execute(text("DELETE FROM tax_profiles WHERE user_id = :id"), {"id": user_id})
                await db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
                await db.commit()
        await engine.dispose()
