"""Admin-only endpoints for account management.

Mounted at /api/v1/admin. Every route is gated by `require_admin`, which
itself wraps `get_current_active_user` — so an inactive or non-admin user
gets a 403 before any handler logic runs.

The three powers exposed here (decided with Mohammad):
- PATCH tier (any direction, including downgrade to Basic) and is_active
- Reset the current-month MonthlyUsage row (conflict-fix path)
- View list, detail, and snapshot stats

No destructive actions (no delete), no chat-history viewing — privacy boundary
intentionally drawn here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.tier_limits import (
    TIER_LIMITS,
    allowed_models_payload,
    current_usage_month,
    get_tier_limits,
    normalize_tier,
)
from app.auth.usage import get_monthly_usage
from app.models.connection import get_db
from app.models.database import (
    ChatSession,
    Document,
    MonthlyUsage,
    SecurityAuditEvent,
    TaxProfile,
    UsageReservation,
    User,
)
from app.models.schemas import (
    AdminStats,
    AdminTierCount,
    AdminUserDetail,
    AdminUserList,
    AdminUserRow,
    AdminUserUpdate,
    UsageCounter,
)

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


def _counter(used: int, limit: int) -> UsageCounter:
    return UsageCounter(used=used, limit=limit, remaining=max(limit - used, 0))


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Snapshot counts for the admin overview page."""
    month = current_usage_month()

    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (
        await db.execute(
            select(func.count(User.id)).where(User.is_active.is_(True))
        )
    ).scalar_one()
    admins = (
        await db.execute(
            select(func.count(User.id)).where(User.is_admin.is_(True))
        )
    ).scalar_one()
    signups_this_month = (
        await db.execute(
            select(func.count(User.id)).where(User.created_at >= month)
        )
    ).scalar_one()

    tier_rows = (
        await db.execute(
            select(User.subscription_tier, func.count(User.id)).group_by(
                User.subscription_tier
            )
        )
    ).all()
    # Force a row per known tier even if count is 0.
    tier_map = {normalize_tier(t): c for t, c in tier_rows}
    tier_counts = [
        AdminTierCount(tier=t, count=tier_map.get(t, 0)) for t in TIER_LIMITS
    ]

    messages_this_month = (
        await db.execute(
            select(func.coalesce(func.sum(MonthlyUsage.message_count), 0)).where(
                MonthlyUsage.usage_month == month
            )
        )
    ).scalar_one()
    docs_this_month = (
        await db.execute(
            select(func.coalesce(func.sum(MonthlyUsage.doc_count), 0)).where(
                MonthlyUsage.usage_month == month
            )
        )
    ).scalar_one()
    total_documents = (
        await db.execute(select(func.count(Document.id)))
    ).scalar_one()
    total_chat_sessions = (
        await db.execute(select(func.count(ChatSession.id)))
    ).scalar_one()

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        inactive_users=total_users - active_users,
        admins=admins,
        signups_this_month=signups_this_month,
        tier_counts=tier_counts,
        messages_this_month=int(messages_this_month or 0),
        docs_this_month=int(docs_this_month or 0),
        total_documents=total_documents,
        total_chat_sessions=total_chat_sessions,
    )


@router.get("/users", response_model=AdminUserList)
async def list_admin_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
    q: str | None = Query(None, description="Substring match on username or name"),
    tier: str | None = Query(None, description="Filter by exact subscription tier"),
    active: bool | None = Query(None, description="Filter by is_active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    """Paginated user list. Search by username/name, filter by tier or active."""
    base = select(User)
    count_base = select(func.count(User.id))

    if q:
        like = f"%{q.lower()}%"
        cond = or_(func.lower(User.username).like(like), func.lower(User.name).like(like))
        base = base.where(cond)
        count_base = count_base.where(cond)
    if tier is not None:
        # Don't normalize — caller picks an exact tier; unknown values yield 0 rows.
        base = base.where(User.subscription_tier == tier)
        count_base = count_base.where(User.subscription_tier == tier)
    if active is not None:
        base = base.where(User.is_active.is_(active))
        count_base = count_base.where(User.is_active.is_(active))

    total = (await db.execute(count_base)).scalar_one()
    rows = (
        await db.execute(
            base.order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return AdminUserList(
        items=[AdminUserRow.model_validate(u) for u in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _build_user_detail(user: User, db: AsyncSession) -> AdminUserDetail:
    tier = normalize_tier(user.subscription_tier)
    limits = get_tier_limits(tier)
    month = current_usage_month()
    usage = await get_monthly_usage(db, user.id, month)
    messages_used = usage.message_count if usage else 0
    docs_used = usage.doc_count if usage else 0

    document_count = (
        await db.execute(
            select(func.count(Document.id)).where(Document.user_id == user.id)
        )
    ).scalar_one()
    tax_profile_count = (
        await db.execute(
            select(func.count(TaxProfile.id)).where(TaxProfile.user_id == user.id)
        )
    ).scalar_one()

    return AdminUserDetail(
        id=user.id,
        username=user.username,
        name=user.name,
        phone=user.phone,
        created_at=user.created_at,
        is_active=user.is_active,
        is_admin=user.is_admin,
        subscription_tier=tier,
        avatar_url=user.avatar_url,
        usage_month=month,
        messages=_counter(messages_used, limits.max_messages_per_month),
        docs=_counter(docs_used, limits.max_docs_per_month),
        document_count=document_count,
        tax_profile_count=tax_profile_count,
    )


async def _get_user_or_404(user_id: uuid.UUID, db: AsyncSession) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_admin_user_detail(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    user = await _get_user_or_404(user_id, db)
    # Echo allowed models alongside detail via the existing helper if needed by UI.
    _ = allowed_models_payload(user.subscription_tier)
    return await _build_user_detail(user, db)


@router.patch("/users/{user_id}", response_model=AdminUserDetail)
async def patch_admin_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Allow tier change (any direction) and is_active toggle.

    Self-deactivation is blocked so an admin can't accidentally lock themselves
    out. Tier change is unrestricted on purpose — the whole point of this
    endpoint is to fix conflicts the user-facing /me/tier flow won't allow.
    """
    user = await _get_user_or_404(user_id, db)

    changed = False
    if data.subscription_tier is not None and data.subscription_tier != user.subscription_tier:
        user.subscription_tier = data.subscription_tier
        changed = True
    if data.is_active is not None and data.is_active != user.is_active:
        if user.id == admin.id and data.is_active is False:
            raise HTTPException(
                status_code=400,
                detail="You cannot deactivate your own admin account.",
            )
        user.is_active = data.is_active
        changed = True

    if changed:
        db.add(SecurityAuditEvent(
            action="admin.user_update", actor_user_id=admin.id, target_user_id=user.id,
        ))
        await db.commit()
        await db.refresh(user)

    return await _build_user_detail(user, db)


@router.post("/users/{user_id}/usage/reset", response_model=AdminUserDetail)
async def reset_admin_user_usage(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Zero out the current month's quota, preserving reservation history.

    Conflict-fix path for cases where a user reports they've been over-charged
    against their quota (e.g. a retry loop spent messages they didn't get
    answers for). If no row exists yet for the current month, this is a no-op.
    """
    user = await _get_user_or_404(user_id, db)
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    usage = await get_monthly_usage(db, user.id, current_usage_month())
    if usage is not None:
        usage.message_count = 0
        usage.doc_count = 0
    await db.execute(update(UsageReservation).where(
        UsageReservation.user_id == user.id,
        UsageReservation.usage_month == current_usage_month(),
        UsageReservation.status.in_(["reserved", "settled"]),
    ).values(status="admin_reset"))
    db.add(SecurityAuditEvent(
        action="admin.usage_reset", actor_user_id=admin.id, target_user_id=user.id,
    ))
    await db.commit()
    return await _build_user_detail(user, db)
