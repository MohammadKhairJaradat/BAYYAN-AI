from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tier_limits import current_usage_month, operation_limit
from app.models.database import MonthlyUsage, UsageReservation, User

_COUNTER_FIELDS = {"chat": "message_count", "document_upload": "doc_count"}
_ACTIVE_STATUSES = {"reserved", "settled"}


async def get_monthly_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    usage_month: date | None = None,
) -> MonthlyUsage | None:
    month = usage_month or current_usage_month()
    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.usage_month == month,
        )
    )
    return result.scalar_one_or_none()


async def get_or_create_monthly_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    usage_month: date | None = None,
) -> MonthlyUsage:
    month = usage_month or current_usage_month()
    usage = await get_monthly_usage(db, user_id, month)
    if usage is not None:
        return usage

    usage = MonthlyUsage(user_id=user_id, usage_month=month)
    db.add(usage)
    await db.flush()
    return usage


async def reserve_usage(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    tier: str,
    operation: str,
    idempotency_key: str | None = None,
) -> uuid.UUID:
    """Atomically reserve one operation under the user's PostgreSQL row lock.

    Reservations are committed before any provider call. An identical key is
    never charged again; clients receive 409 and can load the saved resource.
    """
    key = uuid.uuid4().hex if idempotency_key is None else idempotency_key
    if not isinstance(key, str) or not key.strip() or len(key) > 128:
        raise HTTPException(status_code=422, detail="Idempotency-Key must be 1–128 characters")
    limit = operation_limit(tier, operation)
    month = current_usage_month()

    # One lock per account serializes quota checks and the monthly-row insert.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    existing = (await db.execute(select(UsageReservation).where(
        UsageReservation.user_id == user_id,
        UsageReservation.operation == operation,
        UsageReservation.idempotency_key == key,
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"This {operation} request was already {existing.status}")

    counter_field = _COUNTER_FIELDS.get(operation)
    usage = None
    if counter_field:
        usage = await get_or_create_monthly_usage(db, user_id, month)
        used = getattr(usage, counter_field)
    else:
        used = await db.scalar(select(func.count()).select_from(UsageReservation).where(
            UsageReservation.user_id == user_id,
            UsageReservation.usage_month == month,
            UsageReservation.operation == operation,
            UsageReservation.status.in_(_ACTIVE_STATUSES),
        )) or 0
    if used >= limit:
        label = "message" if operation == "chat" else "document upload" if operation == "document_upload" else operation
        raise HTTPException(status_code=429, detail=f"Monthly {label} quota reached for your {tier} plan ({limit}/month).")

    reservation = UsageReservation(
        user_id=user_id, usage_month=month, operation=operation,
        idempotency_key=key, status="reserved",
    )
    db.add(reservation)
    if usage is not None:
        setattr(usage, counter_field, used + 1)
    await db.commit()
    return reservation.id


async def settle_usage(db: AsyncSession, reservation_id: uuid.UUID) -> None:
    await db.execute(update(UsageReservation).where(
        UsageReservation.id == reservation_id,
        UsageReservation.status == "reserved",
    ).values(status="settled", settled_at=datetime.now(timezone.utc)))
    await db.commit()


async def release_usage(db: AsyncSession, reservation_id: uuid.UUID) -> None:
    """Release only work that was aborted before reaching a provider."""
    reservation = await db.get(UsageReservation, reservation_id)
    if reservation is None or reservation.status != "reserved":
        return
    await db.execute(select(User.id).where(User.id == reservation.user_id).with_for_update())
    if counter_field := _COUNTER_FIELDS.get(reservation.operation):
        usage = await get_monthly_usage(db, reservation.user_id, reservation.usage_month)
        if usage is not None:
            setattr(usage, counter_field, max(0, getattr(usage, counter_field) - 1))
    reservation.status = "released"
    reservation.settled_at = datetime.now(timezone.utc)
    await db.commit()
