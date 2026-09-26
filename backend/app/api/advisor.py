import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.advisor import run_advisor
from app.advisor.fingerprint import input_fingerprint
from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import normalize_tier
from app.auth.usage import reserve_usage, settle_usage
from app.models import User
from app.models.connection import get_db
from app.models.database import (
    AdvisorReportSnapshot,
    TaxProfile,
)
from app.models.schemas import AdvisorLatestReport, AdvisorReport, AdvisorRunRequest

router = APIRouter(prefix="/advisor", tags=["advisor"])


async def _get_owned_profile(
    tax_profile_id: uuid.UUID,
    current_user: User,
    db: AsyncSession,
) -> TaxProfile:
    profile = await db.get(TaxProfile, tax_profile_id)
    if not profile or profile.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Tax profile not found")
    return profile


async def _get_snapshot(
    tax_profile_id: uuid.UUID,
    db: AsyncSession,
) -> AdvisorReportSnapshot | None:
    result = await db.execute(
        select(AdvisorReportSnapshot).where(
            AdvisorReportSnapshot.tax_profile_id == tax_profile_id
        )
    )
    return result.scalar_one_or_none()


async def _save_latest_report(
    *,
    current_user: User,
    tax_profile_id: uuid.UUID,
    lang: str,
    report: AdvisorReport,
    input_fingerprint: str,
    db: AsyncSession,
) -> None:
    snapshot = await _get_snapshot(tax_profile_id, db)
    payload = report.model_dump(mode="json")

    if snapshot is None:
        db.add(
            AdvisorReportSnapshot(
                user_id=current_user.id,
                tax_profile_id=tax_profile_id,
                lang=lang,
                report=payload,
                input_fingerprint=input_fingerprint,
            )
        )
    else:
        snapshot.user_id = current_user.id
        snapshot.lang = lang
        snapshot.report = payload
        snapshot.input_fingerprint = input_fingerprint

    await db.commit()


@router.post("/{tax_profile_id}/run", response_model=AdvisorReport)
async def run(
    tax_profile_id: uuid.UUID,
    payload: AdvisorRunRequest | None = None,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
):
    profile = await _get_owned_profile(tax_profile_id, current_user, db)

    lang = (payload.lang if payload else "ar")
    if lang not in {"ar", "en"}:
        raise HTTPException(status_code=400, detail="lang must be 'ar' or 'en'")

    fingerprint = await input_fingerprint(profile, db)
    reservation_id = await reserve_usage(
        db, user_id=current_user.id, tier=normalize_tier(current_user.subscription_tier),
        operation="advisor", idempotency_key=idempotency_key,
    )
    try:
        report = await run_advisor(tax_profile_id, db, lang=lang)
    finally:
        await settle_usage(db, reservation_id)
    await _save_latest_report(
        current_user=current_user,
        tax_profile_id=tax_profile_id,
        lang=lang,
        report=report,
        input_fingerprint=fingerprint,
        db=db,
    )
    return report


@router.get("/{tax_profile_id}/latest", response_model=AdvisorLatestReport | None)
async def latest(
    tax_profile_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile = await _get_owned_profile(tax_profile_id, current_user, db)
    snapshot = await _get_snapshot(tax_profile_id, db)
    if snapshot is None:
        return None

    current_fingerprint = await input_fingerprint(profile, db)
    return AdvisorLatestReport(
        report=AdvisorReport.model_validate(snapshot.report),
        input_fingerprint=snapshot.input_fingerprint,
        is_stale=snapshot.input_fingerprint != current_fingerprint,
        updated_at=snapshot.updated_at,
    )
