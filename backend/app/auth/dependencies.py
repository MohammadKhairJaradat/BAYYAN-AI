import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.connection import get_db
from app.models.database import RefreshSession, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/swagger-login")


def decode_access_token(token: str) -> dict:
    """Decode and validate an access token without requiring FastAPI deps."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError as exc:
        raise ValueError("Invalid access token") from exc

    user_id: str | None = payload.get("sub")
    token_type: str | None = payload.get("type")
    if user_id is None or token_type != "access":
        raise ValueError("Invalid access token")
    return payload


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id: str = payload["sub"]
        user_uuid = uuid.UUID(user_id)
    except (ValueError, KeyError):
        raise credentials_exception

    user = await db.get(User, user_uuid)
    if user is None:
        raise credentials_exception
    try:
        session_uuid = uuid.UUID(payload["sid"])
    except (KeyError, ValueError, TypeError):
        raise credentials_exception
    session = await db.get(RefreshSession, session_uuid)
    expires_at = session.expires_at if session else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if (
        session is None or session.user_id != user_uuid
        or session.revoked_at is not None
        or expires_at is None or expires_at <= datetime.now(timezone.utc)
    ):
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


async def require_admin(
    current_user: User = Depends(get_current_active_user),
) -> User:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
