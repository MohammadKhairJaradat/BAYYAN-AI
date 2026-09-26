"""Optimistic version checks and atomic invalidation of tax snapshots."""

import uuid

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import TaxProfile


async def lock_profile_version(
    db: AsyncSession, profile_id: uuid.UUID, expected_version: int | None = None,
) -> TaxProfile:
    profile = (await db.execute(select(TaxProfile).where(
        TaxProfile.id == profile_id,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Tax profile not found")
    if expected_version is not None and profile.version != expected_version:
        raise HTTPException(status_code=409, detail="Tax profile changed; reload before saving")
    return profile


async def bump_profile_version(db: AsyncSession, profile_id: uuid.UUID) -> None:
    await db.execute(update(TaxProfile).where(TaxProfile.id == profile_id).values(
        version=TaxProfile.version + 1,
    ))
