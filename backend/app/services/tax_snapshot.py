"""One tax-input builder for profile, chat and advisor paths."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.money import format_money
from app.models import DeductionCategory, MaritalStatus
from app.models.database import Deduction, IncomeSource, TaxProfile
from app.tax_engine import TaxInput


def _field(row: Any, name: str, default: Any = None) -> Any:
    return row.get(name, default) if isinstance(row, dict) else getattr(row, name, default)


def build_tax_input(
    profile: TaxProfile | dict,
    income_rows: Sequence[IncomeSource | dict],
    deduction_rows: Sequence[Deduction | dict],
    *,
    exact: bool = False,
) -> TaxInput:
    """Keep legacy floats only at the old response boundary; new paths stay Decimal."""
    def amount(value: Any) -> Decimal | float:
        decimal = Decimal(str(value or 0))
        return decimal if exact else float(decimal)

    zero: Decimal | float = Decimal("0") if exact else 0.0
    deductions: dict[DeductionCategory, Decimal | float] = {}
    for row in deduction_rows:
        try:
            category = DeductionCategory(_field(row, "category"))
        except (ValueError, TypeError):
            if exact:
                raise ValueError("Unsupported stored deduction category") from None
            continue
        deductions[category] = deductions.get(category, zero) + amount(_field(row, "amount"))

    try:
        marital = MaritalStatus(_field(profile, "marital_status"))
    except (ValueError, TypeError):
        if exact:
            raise ValueError("Unsupported stored marital status") from None
        marital = MaritalStatus.single
    return TaxInput(
        gross_income=sum((amount(_field(row, "amount")) for row in income_rows), zero),
        marital_status=marital,
        num_dependents=_field(profile, "num_dependents") or 0,
        residency_status=_field(profile, "residency_status") or "resident",
        claims_dependents_exemption=bool(_field(profile, "claims_dependents_exemption")),
        claim_spouse_expense_exemption=bool(_field(profile, "claim_spouse_expense_exemption")),
        disability_exemption_count=_field(profile, "disability_exemption_count") or 0,
        tax_withheld=sum((amount(_field(row, "tax_withheld")) for row in income_rows), zero),
        deductions=deductions,
    )


@dataclass(frozen=True)
class TaxInputSnapshot:
    profile: TaxProfile
    income_rows: list[IncomeSource]
    deduction_rows: list[Deduction]
    exact_input: TaxInput | None
    legacy_input: TaxInput

    def to_payload(self) -> dict:
        """Canonical, lossless input used for saved-run evidence and its hash."""
        profile = self.profile
        return {
            "profile": {
                "id": str(profile.id), "tax_year": profile.tax_year,
                "version": profile.version, "marital_status": profile.marital_status,
                "num_dependents": profile.num_dependents,
                "filing_status": profile.filing_status,
                "residency_status": profile.residency_status,
                "claims_dependents_exemption": profile.claims_dependents_exemption,
                "claim_spouse_expense_exemption": profile.claim_spouse_expense_exemption,
                "disability_exemption_count": profile.disability_exemption_count,
            },
            "income_sources": sorted(({
                "id": str(row.id), "type": row.type,
                "amount": format_money(row.amount),
                "tax_withheld": format_money(row.tax_withheld),
                "employer_name": row.employer_name,
                "description": row.description,
            } for row in self.income_rows), key=lambda row: row["id"]),
            "deductions": sorted(({
                "id": str(row.id), "category": row.category,
                "amount": format_money(row.amount),
                "date": row.date.isoformat() if row.date else None,
                "description": row.description,
                "document_id": str(row.document_id) if row.document_id else None,
            } for row in self.deduction_rows), key=lambda row: row["id"]),
        }


async def load_tax_snapshot(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
    tax_year: int | None = None,
    include_exact: bool = True,
) -> TaxInputSnapshot | None:
    if (profile_id is None) == (tax_year is None):
        raise ValueError("Specify exactly one profile_id or tax_year")
    stmt = select(TaxProfile).where(TaxProfile.user_id == user_id)
    stmt = stmt.where(TaxProfile.id == profile_id) if profile_id else stmt.where(TaxProfile.tax_year == tax_year)
    profile = (await db.execute(stmt)).scalar_one_or_none()
    if profile is None:
        return None
    income_rows = list((await db.execute(select(IncomeSource).where(
        IncomeSource.tax_profile_id == profile.id,
    ))).scalars().all())
    deduction_rows = list((await db.execute(select(Deduction).where(
        Deduction.tax_profile_id == profile.id,
    ))).scalars().all())
    return TaxInputSnapshot(
        profile=profile, income_rows=income_rows, deduction_rows=deduction_rows,
        exact_input=build_tax_input(profile, income_rows, deduction_rows, exact=True) if include_exact else None,
        legacy_input=build_tax_input(profile, income_rows, deduction_rows),
    )
