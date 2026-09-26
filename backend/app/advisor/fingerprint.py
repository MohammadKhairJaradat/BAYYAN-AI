"""Stable fingerprints for advisor input staleness checks."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import Deduction, IncomeSource, TaxProfile


def _fingerprint_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ),
    )


async def input_fingerprint(profile: TaxProfile, db: AsyncSession) -> str:
    income_rows = (
        await db.execute(
            select(IncomeSource).where(IncomeSource.tax_profile_id == profile.id)
        )
    ).scalars().all()
    deduction_rows = (
        await db.execute(select(Deduction).where(Deduction.tax_profile_id == profile.id))
    ).scalars().all()

    payload = {
        "profile": {
            "tax_year": profile.tax_year,
            "marital_status": profile.marital_status,
            "num_dependents": profile.num_dependents,
            "filing_status": profile.filing_status,
            "residency_status": profile.residency_status,
            "claims_dependents_exemption": profile.claims_dependents_exemption,
            "claim_spouse_expense_exemption": profile.claim_spouse_expense_exemption,
            "disability_exemption_count": profile.disability_exemption_count,
        },
        "income_sources": _sort_rows(
            [
                {
                    "type": item.type,
                    "amount": _fingerprint_value(item.amount),
                    "tax_withheld": _fingerprint_value(item.tax_withheld),
                    "employer_name": item.employer_name,
                    "description": item.description,
                }
                for item in income_rows
            ]
        ),
        "deductions": _sort_rows(
            [
                {
                    "category": item.category,
                    "amount": _fingerprint_value(item.amount),
                    "date": _fingerprint_value(item.date),
                    "description": item.description,
                    "document_id": _fingerprint_value(item.document_id),
                }
                for item in deduction_rows
            ]
        ),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
