import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models.connection import get_db
from app.models.database import IncomeSource, TaxProfile, User
from app.models.schemas import IncomeSourceCreate, IncomeSourceRead, IncomeSourceUpdate
from app.services.profile_version import bump_profile_version, lock_profile_version

router = APIRouter(prefix="/income-sources", tags=["income_sources"])


async def _verify_tax_profile_ownership(
    tax_profile_id: uuid.UUID, user: User, db: AsyncSession
) -> TaxProfile:
    profile = await db.get(TaxProfile, tax_profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tax profile not found")
    return profile


@router.post("/", response_model=IncomeSourceRead, status_code=201)
async def create_income_source(
    data: IncomeSourceCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    await _verify_tax_profile_ownership(data.tax_profile_id, current_user, db)
    await lock_profile_version(db, data.tax_profile_id, if_match)
    source = IncomeSource(**data.model_dump())
    db.add(source)
    await bump_profile_version(db, data.tax_profile_id)
    await db.commit()
    await db.refresh(source)
    return source


@router.get("/", response_model=list[IncomeSourceRead])
async def list_income_sources(
    tax_profile_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(IncomeSource)
        .join(TaxProfile)
        .where(TaxProfile.user_id == current_user.id)
    )
    if tax_profile_id:
        stmt = stmt.where(IncomeSource.tax_profile_id == tax_profile_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{source_id}", response_model=IncomeSourceRead)
async def get_income_source(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(IncomeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")
    await _verify_tax_profile_ownership(source.tax_profile_id, current_user, db)
    return source


@router.put("/{source_id}", response_model=IncomeSourceRead)
async def update_income_source(
    source_id: uuid.UUID,
    data: IncomeSourceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    source = await db.get(IncomeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")
    await _verify_tax_profile_ownership(source.tax_profile_id, current_user, db)
    await lock_profile_version(db, source.tax_profile_id, if_match)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    if data.model_fields_set:
        await bump_profile_version(db, source.tax_profile_id)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_income_source(
    source_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    source = await db.get(IncomeSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Income source not found")
    await _verify_tax_profile_ownership(source.tax_profile_id, current_user, db)
    await lock_profile_version(db, source.tax_profile_id, if_match)
    await db.delete(source)
    await bump_profile_version(db, source.tax_profile_id)
    await db.commit()
    return Response(status_code=204)
