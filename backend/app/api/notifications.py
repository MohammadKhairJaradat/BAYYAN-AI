"""Synthesized notifications based on user state. No persistence yet."""
import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.models.connection import get_db
from app.models.database import (
    Document,
    IncomeSource,
    TaxProfile,
    User,
)
from app.models.schemas import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/", response_model=list[Notification])
async def list_notifications(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    current_year = today.year
    notifications: list[Notification] = []

    current_profile_stmt = select(TaxProfile).where(
        TaxProfile.user_id == current_user.id,
        TaxProfile.tax_year == current_year,
    )
    current_profile = (await db.execute(current_profile_stmt)).scalar_one_or_none()

    docs_count = (
        await db.execute(
            select(func.count(Document.id)).where(Document.user_id == current_user.id)
        )
    ).scalar_one()

    if current_profile is None:
        notifications.append(
            Notification(
                id="no-profile",
                title="Set up your tax profile",
                message=f"You haven't set up a tax profile for {current_year} yet.",
                severity="action",
                link="/advisor",
                created_at=now,
            )
        )
    else:
        income_count = (
            await db.execute(
                select(func.count(IncomeSource.id)).where(
                    IncomeSource.tax_profile_id == current_profile.id
                )
            )
        ).scalar_one()
        if income_count == 0:
            notifications.append(
                Notification(
                    id="no-income",
                    title="Add an income source",
                    message=f"Add at least one income source for tax year {current_year} to run the advisor.",
                    severity="action",
                    link="/advisor",
                    created_at=now,
                )
            )

    if docs_count == 0:
        notifications.append(
            Notification(
                id="no-documents",
                title="Upload your first document",
                message="Upload a salary slip, receipt, or bank statement to start building your profile.",
                severity="info",
                link="/files",
                created_at=now,
            )
        )

    deadline = dt.date(current_year, 4, 30)
    days_to_deadline = (deadline - today).days
    if 0 <= days_to_deadline <= 30:
        notifications.append(
            Notification(
                id="deadline-soon",
                title="Tax filing deadline approaching",
                message=f"The income tax filing deadline is on April 30 ({days_to_deadline} days away).",
                severity="warning",
                link="/advisor",
                created_at=now,
            )
        )

    return notifications
