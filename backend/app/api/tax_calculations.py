import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models import User
from app.models.connection import get_db
from app.models.schemas import TaxCalculationResult, TaxCalculationResultV2
from app.services.tax_snapshot import load_tax_snapshot
from app.tax_engine import calculate_tax
from app.tax_engine.decimal_engine import calculate_decimal

router = APIRouter(prefix="/tax-calculations", tags=["tax_calculations"])


@router.post("/{tax_profile_id}/calculate-v2", response_model=TaxCalculationResultV2)
async def calculate_for_profile_v2(
    tax_profile_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Exact-money preview of the current demonstration rules; no history write."""
    try:
        snapshot = await load_tax_snapshot(db, user_id=current_user.id, profile_id=tax_profile_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Tax profile not found")
        assert snapshot.exact_input is not None
        result = calculate_decimal(snapshot.exact_input, tax_year=snapshot.profile.tax_year)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tax_profile_id": tax_profile_id, **result.to_payload()}


@router.post("/{tax_profile_id}/calculate", response_model=TaxCalculationResult)
async def calculate_for_profile(
    tax_profile_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await load_tax_snapshot(db, user_id=current_user.id, profile_id=tax_profile_id, include_exact=False)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Tax profile not found")
    breakdown = calculate_tax(snapshot.legacy_input)

    return TaxCalculationResult(
        tax_profile_id=tax_profile_id,
        gross_income=breakdown.gross_income,
        personal_exemption=breakdown.personal_exemption,
        family_exemption=breakdown.family_exemption,
        expense_exemption=breakdown.expense_exemption,
        disability_exemption=breakdown.disability_exemption,
        total_exemptions=breakdown.total_exemptions,
        deductions_allowed={k.value: v for k, v in breakdown.deductions_allowed.items()},
        deductions_disallowed={
            k.value: v for k, v in breakdown.deductions_disallowed.items()
        },
        total_deductions=breakdown.total_deductions,
        taxable_income=breakdown.taxable_income,
        bracket_breakdown=breakdown.bracket_breakdown,
        national_contribution=breakdown.national_contribution,
        tax_liability=breakdown.tax_liability,
        total_tax_withheld=breakdown.total_tax_withheld,
        net_tax_due=breakdown.net_tax_due,
        refund_due=breakdown.refund_due,
        effective_rate=breakdown.effective_rate,
        marginal_rate=breakdown.marginal_rate,
    )
