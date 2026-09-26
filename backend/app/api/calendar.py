"""Calendar events: fixed Jordanian tax deadlines + user filing history."""
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models.connection import get_db
from app.models.database import FilingHistory, TaxProfile, User
from app.models.schemas import CalendarEvent

router = APIRouter(prefix="/calendar", tags=["calendar"])


# Hardcoded Jordanian tax deadlines per year (rules are stable; refresh annually).
_FIXED_DEADLINES: list[tuple[int, int, str, str]] = [
    (
        4,
        30,
        "Income Tax Filing Deadline",
        "Deadline for individuals to file the annual income tax return (Law No. 34/2014).",
    ),
    (
        1,
        31,
        "Q4 Withholding Tax",
        "Deadline for employers to remit Q4 withholding tax.",
    ),
    (
        7,
        31,
        "Q2 Withholding Tax",
        "Deadline for employers to remit Q2 withholding tax.",
    ),
]


@router.get("/events", response_model=list[CalendarEvent])
async def list_events(
    year: int = Query(..., ge=2000, le=2100),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    events: list[CalendarEvent] = []

    for month, day, title, description in _FIXED_DEADLINES:
        events.append(
            CalendarEvent(
                date=dt.date(year, month, day),
                title=title,
                type="deadline",
                description=description,
            )
        )

    profile_ids_stmt = select(TaxProfile.id).where(TaxProfile.user_id == current_user.id)
    profile_ids = [r for r in (await db.execute(profile_ids_stmt)).scalars().all()]

    if profile_ids:
        filing_stmt = select(FilingHistory).where(
            FilingHistory.tax_profile_id.in_(profile_ids)
        )
        filings = (await db.execute(filing_stmt)).scalars().all()
        for f in filings:
            filed_date = f.filed_at.date()
            if filed_date.year != year:
                continue
            events.append(
                CalendarEvent(
                    date=filed_date,
                    title="Tax Return Filed",
                    type="filing",
                    description=(
                        f"Tax liability: {float(f.tax_liability or 0):,.0f} JD"
                        if f.tax_liability is not None
                        else None
                    ),
                )
            )

    events.sort(key=lambda e: e.date)
    return events
