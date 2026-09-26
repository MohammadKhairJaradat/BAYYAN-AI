"""Quota ledger and admin correction behavior without external providers."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.admin import reset_admin_user_usage
from app.auth.tier_limits import current_usage_month
from app.auth.usage import get_monthly_usage, release_usage, reserve_usage, settle_usage
from app.models.database import SecurityAuditEvent, UsageReservation, User


@pytest.mark.asyncio
async def test_release_before_provider_restores_counter_and_key_cannot_be_reused(db_session):
    user = User(username=f"s05-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S05")
    db_session.add(user)
    await db_session.commit()

    reservation_id = await reserve_usage(
        db_session, user_id=user.id, tier="Basic", operation="chat", idempotency_key="one",
    )
    usage = await get_monthly_usage(db_session, user.id)
    assert usage.message_count == 1

    await release_usage(db_session, reservation_id)
    await db_session.refresh(usage)
    assert usage.message_count == 0
    assert (await db_session.get(UsageReservation, reservation_id)).status == "released"

    with pytest.raises(HTTPException) as replay:
        await reserve_usage(db_session, user_id=user.id, tier="Basic", operation="chat", idempotency_key="one")
    assert replay.value.status_code == 409

    with pytest.raises(HTTPException) as bad_key:
        await reserve_usage(db_session, user_id=user.id, tier="Basic", operation="chat", idempotency_key="")
    assert bad_key.value.status_code == 422


@pytest.mark.asyncio
async def test_admin_reset_releases_all_operation_quotas_and_is_audited(db_session):
    admin = User(username=f"admin-{uuid.uuid4().hex}@example.com", hashed_password="test", name="Admin", is_admin=True)
    user = User(username=f"s05-{uuid.uuid4().hex}@example.com", hashed_password="test", name="S05", subscription_tier="Pro")
    db_session.add_all([admin, user])
    await db_session.commit()

    chat_id = await reserve_usage(db_session, user_id=user.id, tier="Pro", operation="chat", idempotency_key="chat")
    await settle_usage(db_session, chat_id)
    advisor_id = await reserve_usage(db_session, user_id=user.id, tier="Pro", operation="advisor", idempotency_key="advisor")
    await settle_usage(db_session, advisor_id)

    detail = await reset_admin_user_usage(user.id, db_session, admin)
    assert detail.messages.used == 0
    rows = (await db_session.execute(select(UsageReservation).where(
        UsageReservation.user_id == user.id,
        UsageReservation.usage_month == current_usage_month(),
    ))).scalars().all()
    assert len(rows) == 2
    assert all(row.status == "admin_reset" for row in rows)
    events = (await db_session.execute(select(SecurityAuditEvent).where(
        SecurityAuditEvent.target_user_id == user.id,
        SecurityAuditEvent.action == "admin.usage_reset",
    ))).scalars().all()
    assert len(events) == 1

    await reserve_usage(db_session, user_id=user.id, tier="Pro", operation="advisor", idempotency_key="advisor-new")
