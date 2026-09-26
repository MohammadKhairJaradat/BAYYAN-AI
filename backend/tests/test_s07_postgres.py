"""Run with S07_POSTGRES_URL against an isolated PostgreSQL DB at migration 021."""

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.database import IncomeSource, TaxProfile, User


@pytest.mark.asyncio
async def test_postgres_preserves_fils_and_wider_numeric_column():
    url = os.environ.get("S07_POSTGRES_URL")
    if not url:
        pytest.skip("Set S07_POSTGRES_URL to an isolated migrated PostgreSQL database")

    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            column = (await db.execute(text("""
                SELECT numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = 'income_sources' AND column_name = 'amount'
            """))).one()
            assert column == (15, 3)

            user = User(username=f"s07-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S07")
            db.add(user)
            await db.flush()
            profile = TaxProfile(user_id=user.id, tax_year=2026, marital_status="single")
            db.add(profile)
            await db.flush()
            source = IncomeSource(tax_profile_id=profile.id, type="salary", amount=Decimal("123.456"), tax_withheld=Decimal("0.001"))
            db.add(source)
            await db.commit()
            source_id = source.id

        async with sessions() as db:
            loaded = await db.get(IncomeSource, source_id)
            assert loaded.amount == Decimal("123.456")
            assert loaded.tax_withheld == Decimal("0.001")
    finally:
        await engine.dispose()
