from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.auth.tier_limits import (
    allowed_models_payload,
    current_usage_month,
    get_tier_limits,
    normalize_tier,
)
from app.auth.usage import get_monthly_usage
from app.config import settings
from app.models.connection import get_db
from app.models.database import User
from app.models.schemas import UserRead, UserUpdate, UserUsageRead
from app.services.storage import StorageService, get_storage
from app.services.file_validation import matches_image_or_pdf

router = APIRouter(prefix="/users", tags=["users"])


ALLOWED_AVATAR_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_AVATAR_BYTES = 10 * 1024 * 1024  # 10 MiB
CHUNK = 1 << 20  # 1 MiB
EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def _counter(used: int, limit: int) -> dict[str, int]:
    return {
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
    }


async def _build_usage_response(
    current_user: User,
    db: AsyncSession,
) -> UserUsageRead:
    tier = normalize_tier(current_user.subscription_tier)
    limits = get_tier_limits(tier)
    month = current_usage_month()
    usage = await get_monthly_usage(db, current_user.id, month)
    message_count = usage.message_count if usage else 0
    doc_count = usage.doc_count if usage else 0

    return UserUsageRead(
        tier=tier,
        usage_month=month,
        messages=_counter(message_count, limits.max_messages_per_month),
        docs=_counter(doc_count, limits.max_docs_per_month),
        allowed_models=allowed_models_payload(tier),
        max_tokens=limits.max_tokens,
    )


@router.get("/me", response_model=UserRead)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user),
):
    return current_user


@router.put("/me", response_model=UserRead)
async def update_current_user_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/me/usage", response_model=UserUsageRead)
async def get_current_user_usage(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _build_usage_response(current_user, db)


@router.post("/me/avatar", response_model=UserRead)
async def upload_current_user_avatar(
    file: UploadFile,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    ext = PurePosixPath(file.filename or "").suffix.lstrip(".").lower()
    if ext not in ALLOWED_AVATAR_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {sorted(ALLOWED_AVATAR_EXT)}",
        )

    buffer = bytearray()
    while chunk := await file.read(CHUNK):
        buffer.extend(chunk)
        if len(buffer) > MAX_AVATAR_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {MAX_AVATAR_BYTES} bytes",
            )

    if not matches_image_or_pdf(buffer, ext) or file.content_type != EXT_TO_MIME[ext]:
        raise HTTPException(status_code=400, detail="File contents do not match its image type")

    content_type = EXT_TO_MIME[ext]
    if ext == "jpeg":
        ext = "jpg"

    # Wipe any previous file (potentially under a different extension) so we
    # never leave orphan objects when the user switches png → webp etc.
    await storage.delete_avatar(current_user.id)
    _key, mtime = await storage.upload_avatar(
        bytes(buffer), current_user.id, ext, content_type
    )

    current_user.avatar_url = (
        f"{settings.MINIO_PUBLIC_URL}/{settings.MINIO_AVATAR_BUCKET}"
        f"/{current_user.id}.{ext}?v={mtime}"
    )
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.delete("/me/avatar", response_model=UserRead)
async def delete_current_user_avatar(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageService = Depends(get_storage),
):
    await storage.delete_avatar(current_user.id)
    current_user.avatar_url = None
    await db.commit()
    await db.refresh(current_user)
    return current_user
