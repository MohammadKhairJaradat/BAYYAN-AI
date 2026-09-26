import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models.connection import get_db
from app.models.database import Deduction, Document, TaxProfile, User
from app.models.schemas import DeductionCreate, DeductionRead, DeductionUpdate
from app.services.profile_version import bump_profile_version, lock_profile_version

router = APIRouter(prefix="/deductions", tags=["deductions"])


async def _verify_tax_profile_ownership(
    tax_profile_id: uuid.UUID, user: User, db: AsyncSession
) -> TaxProfile:
    profile = await db.get(TaxProfile, tax_profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tax profile not found")
    return profile


async def _verify_document_ownership(
    document_id: uuid.UUID | None, user: User, db: AsyncSession
) -> None:
    if document_id is None:
        return
    document = await db.get(Document, document_id)
    if document is None or document.user_id != user.id:
        raise HTTPException(status_code=404, detail="Document not found")


@router.post("/", response_model=DeductionRead, status_code=201)
async def create_deduction(
    data: DeductionCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    await _verify_tax_profile_ownership(data.tax_profile_id, current_user, db)
    await lock_profile_version(db, data.tax_profile_id, if_match)
    await _verify_document_ownership(data.document_id, current_user, db)
    deduction = Deduction(**data.model_dump())
    db.add(deduction)
    try:
        await bump_profile_version(db, data.tax_profile_id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Document already has a linked deduction") from exc
    await db.refresh(deduction)
    return deduction


@router.get("/", response_model=list[DeductionRead])
async def list_deductions(
    tax_profile_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Deduction)
        .join(TaxProfile)
        .where(TaxProfile.user_id == current_user.id)
    )
    if tax_profile_id:
        stmt = stmt.where(Deduction.tax_profile_id == tax_profile_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{deduction_id}", response_model=DeductionRead)
async def get_deduction(
    deduction_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    deduction = await db.get(Deduction, deduction_id)
    if not deduction:
        raise HTTPException(status_code=404, detail="Deduction not found")
    await _verify_tax_profile_ownership(deduction.tax_profile_id, current_user, db)
    return deduction


@router.put("/{deduction_id}", response_model=DeductionRead)
async def update_deduction(
    deduction_id: uuid.UUID,
    data: DeductionUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    deduction = await db.get(Deduction, deduction_id)
    if not deduction:
        raise HTTPException(status_code=404, detail="Deduction not found")
    await _verify_tax_profile_ownership(deduction.tax_profile_id, current_user, db)
    await lock_profile_version(db, deduction.tax_profile_id, if_match)
    if "document_id" in data.model_fields_set:
        await _verify_document_ownership(data.document_id, current_user, db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(deduction, field, value)
    try:
        if data.model_fields_set:
            await bump_profile_version(db, deduction.tax_profile_id)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Document already has a linked deduction") from exc
    await db.refresh(deduction)
    return deduction


@router.delete("/{deduction_id}", status_code=204)
async def delete_deduction(
    deduction_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    if_match: int | None = Header(None, alias="If-Match"),
):
    deduction = await db.get(Deduction, deduction_id)
    if not deduction:
        raise HTTPException(status_code=404, detail="Deduction not found")
    await _verify_tax_profile_ownership(deduction.tax_profile_id, current_user, db)
    await lock_profile_version(db, deduction.tax_profile_id, if_match)
    await db.delete(deduction)
    await bump_profile_version(db, deduction.tax_profile_id)
    await db.commit()
    return Response(status_code=204)
