"""Year-scoped demonstration calculations and append-only review history."""

import hashlib
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models.connection import get_db
from app.models.database import CalculationRun, TaxProfile, User
from app.services.profile_version import lock_profile_version
from app.services.tax_snapshot import TaxInputSnapshot, load_tax_snapshot
from app.tax_engine.decimal_engine import calculate_decimal

router = APIRouter(prefix="/tax-workspace", tags=["tax_workspace"])


class SaveCalculationRequest(BaseModel):
    expected_version: int = Field(ge=1)


def _calculate(snapshot: TaxInputSnapshot) -> dict:
    assert snapshot.exact_input is not None
    try:
        return calculate_decimal(snapshot.exact_input, tax_year=snapshot.profile.tax_year).to_payload()
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _run_payload(
    run: CalculationRun, *, current_version: int | None = None,
    current_profile_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": run.id,
        "tax_profile_id": run.tax_profile_id,
        "tax_year": run.tax_year,
        "profile_version": run.profile_version,
        "ruleset_id": run.ruleset_id,
        "input_fingerprint": run.input_fingerprint,
        "input_snapshot": run.input_snapshot,
        "output_snapshot": run.output_snapshot,
        "created_at": run.created_at,
        "stale": (current_version is None or run.profile_version != current_version
                  or run.tax_profile_id != current_profile_id),
    }


async def _latest_run(db: AsyncSession, user_id: uuid.UUID, year: int) -> CalculationRun | None:
    return (await db.execute(select(CalculationRun).where(
        CalculationRun.user_id == user_id, CalculationRun.tax_year == year,
    ).order_by(CalculationRun.created_at.desc(), CalculationRun.id.desc()).limit(1))).scalar_one_or_none()


@router.get("/{year}")
async def preview_workspace(
    year: int = Path(ge=2000, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await load_tax_snapshot(db, user_id=current_user.id, tax_year=year)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tax profile not found for this year")
    output = _calculate(snapshot)
    latest = await _latest_run(db, current_user.id, year)
    return {
        "tax_year": year, "profile_id": snapshot.profile.id,
        "profile_version": snapshot.profile.version,
        "input_snapshot": snapshot.to_payload(), "preview": output,
        "latest_run": _run_payload(latest, current_version=snapshot.profile.version,
                                   current_profile_id=snapshot.profile.id) if latest else None,
    }


@router.post("/{year}/runs", status_code=201)
async def save_calculation(
    data: SaveCalculationRequest,
    year: int = Path(ge=2000, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    profile_id = (await db.execute(select(TaxProfile.id).where(
        TaxProfile.user_id == current_user.id, TaxProfile.tax_year == year,
    ))).scalar_one_or_none()
    if profile_id is None:
        raise HTTPException(status_code=404, detail="Tax profile not found for this year")
    await lock_profile_version(db, profile_id, data.expected_version)
    # Read rows after acquiring the profile lock: all sanctioned tax-input edits
    # take that same lock before writing, so this is one consistent version.
    snapshot = await load_tax_snapshot(db, user_id=current_user.id, tax_year=year)
    assert snapshot is not None
    output = _calculate(snapshot)
    input_payload = snapshot.to_payload()
    canonical = json.dumps(input_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    run = CalculationRun(
        user_id=current_user.id,
        tax_profile_id=snapshot.profile.id,
        tax_year=year,
        profile_version=snapshot.profile.version,
        ruleset_id=output["ruleset_id"],
        input_fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        input_snapshot=input_payload,
        output_snapshot=output,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _run_payload(run, current_version=snapshot.profile.version,
                        current_profile_id=snapshot.profile.id)


@router.get("/{year}/runs")
async def list_calculation_runs(
    year: int = Path(ge=2000, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await load_tax_snapshot(db, user_id=current_user.id, tax_year=year, include_exact=False)
    runs = (await db.execute(select(CalculationRun).where(
        CalculationRun.user_id == current_user.id, CalculationRun.tax_year == year,
    ).order_by(CalculationRun.created_at.desc(), CalculationRun.id.desc()))).scalars().all()
    current_version = snapshot.profile.version if snapshot else None
    return [_run_payload(run, current_version=current_version,
                         current_profile_id=snapshot.profile.id if snapshot else None) for run in runs]
