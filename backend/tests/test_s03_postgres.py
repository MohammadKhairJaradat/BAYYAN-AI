"""Run with S03_POSTGRES_URL against an isolated migrated PostgreSQL database."""

import asyncio
import os
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import document_processing
from app.extraction.base import DeductionCategory, DocumentType, ExtractionResult
from app.models.database import Deduction, Document, TaxProfile, User


@pytest.mark.asyncio
async def test_postgres_concurrent_processing_has_one_deduction(monkeypatch):
    url = os.environ.get("S03_POSTGRES_URL")
    if not url:
        pytest.skip("Set S03_POSTGRES_URL to an isolated migrated PostgreSQL database")

    engine = create_async_engine(url, pool_size=3)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            user = User(username=f"s03-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S03", subscription_tier="Pro")
            db.add(user)
            await db.flush()
            profile = TaxProfile(user_id=user.id, tax_year=2026, marital_status="single")
            doc = Document(user_id=user.id, file_path="test", original_filename="test.png", document_type="receipt")
            db.add_all([profile, doc])
            await db.commit()
            user_id, profile_id, doc_id = user.id, profile.id, doc.id

        class Storage:
            async def download_file(self, _path):
                return b"\x89PNG\r\n\x1a\nimage"

        async def extract(_data, *, mime_type):
            await asyncio.sleep(0.05)
            return ExtractionResult(amount=100, category=DeductionCategory.MEDICAL, document_type=DocumentType.RECEIPT, confidence=0.99)

        monkeypatch.setattr(document_processing, "extract_document", extract)

        async def process():
            async with sessions() as db:
                current_user = await db.get(User, user_id)
                return await document_processing.process_document(
                    doc_id, tax_profile_id=profile_id, current_user=current_user,
                    db=db, storage=Storage(), idempotency_key=None,
                )

        first, second = await asyncio.gather(process(), process())
        assert first.deduction_id == second.deduction_id
        async with sessions() as db:
            count = await db.scalar(select(func.count()).select_from(Deduction).where(Deduction.document_id == doc_id))
            assert count == 1
            db.add(Deduction(tax_profile_id=profile_id, category="medical", amount=10, document_id=doc_id))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        await engine.dispose()
