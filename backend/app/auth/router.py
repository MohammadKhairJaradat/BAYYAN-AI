"""Credential login and server-backed refresh sessions."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.auth.security import create_access_token, create_refresh_token, hash_password, token_hash, verify_password
from app.config import settings
from app.models.connection import get_db
from app.models.database import RefreshSession, SecurityAuditEvent, User
from app.models.schemas import LoginRequest, TokenResponse, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_NAME = "bayyan_refresh"
COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path=COOKIE_PATH, httponly=True, secure=settings.APP_ENV == "production",
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, secure=settings.APP_ENV == "production", samesite="lax")


def _require_trusted_origin(request: Request, *, required: bool = True) -> None:
    origin = request.headers.get("origin")
    allowed = {settings.FRONTEND_ORIGIN.rstrip("/")}
    if settings.APP_ENV != "production":
        allowed.update({
            "http://localhost:5173", "http://127.0.0.1:5173",
            "http://localhost:8000", "http://127.0.0.1:8000",
        })
    if (required or origin is not None) and origin not in allowed:
        raise HTTPException(status_code=403, detail="Untrusted request origin")


async def _authenticate(username: str, password: str, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password) or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def _start_session(user: User, db: AsyncSession, response: Response) -> TokenResponse:
    session_id = uuid.uuid4()
    token = create_refresh_token({"sub": str(user.id), "sid": str(session_id), "jti": str(uuid.uuid4())})
    payload = jwt.get_unverified_claims(token)
    db.add(RefreshSession(
        id=session_id, user_id=user.id, token_hash=token_hash(token),
        expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc),
    ))
    db.add(SecurityAuditEvent(action="auth.login", actor_user_id=user.id, session_id=session_id))
    await db.commit()
    _set_refresh_cookie(response, token)
    return TokenResponse(access_token=create_access_token({"sub": str(user.id), "sid": str(session_id)}))


@router.post("/signup", response_model=UserRead, status_code=201)
async def signup(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(User.username == data.username))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(username=data.username, hashed_password=hash_password(data.password), name=data.name, phone=data.phone)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request, required=False)
    user = await _authenticate(data.username, data.password, db)
    return await _start_session(user, db, response)


@router.post("/swagger-login", response_model=TokenResponse, include_in_schema=False)
async def swagger_login(request: Request, response: Response, data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request, required=False)
    user = await _authenticate(data.username, data.password, db)
    return await _start_session(user, db, response)


def _decode_refresh(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        if payload.get("type") != "refresh":
            raise ValueError("Wrong token type")
        return uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
    except (JWTError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid refresh token") from exc


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request)
    old_token = request.cookies.get(COOKIE_NAME)
    if not old_token:
        raise HTTPException(status_code=401, detail="Missing refresh cookie")
    user_id, session_id = _decode_refresh(old_token)
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive or missing account")

    new_token = create_refresh_token({"sub": str(user_id), "sid": str(session_id), "jti": str(uuid.uuid4())})
    expires_at = datetime.fromtimestamp(jwt.get_unverified_claims(new_token)["exp"], timezone.utc)
    changed = await db.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == user_id,
            RefreshSession.token_hash == token_hash(old_token),
            RefreshSession.revoked_at.is_(None),
            RefreshSession.expires_at > datetime.now(timezone.utc),
        )
        .values(token_hash=token_hash(new_token), expires_at=expires_at)
        .returning(RefreshSession.id)
    )
    if changed.scalar_one_or_none() is None:
        await db.rollback()
        raise HTTPException(status_code=401, detail="Refresh token already used or revoked")
    db.add(SecurityAuditEvent(action="auth.refresh", actor_user_id=user_id, session_id=session_id))
    await db.commit()
    _set_refresh_cookie(response, new_token)
    return TokenResponse(access_token=create_access_token({"sub": str(user_id), "sid": str(session_id)}))


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    _require_trusted_origin(request)
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            user_id, session_id = _decode_refresh(token)
        except HTTPException:
            pass
        else:
            changed = await db.execute(
                update(RefreshSession)
                .where(
                    RefreshSession.id == session_id,
                    RefreshSession.user_id == user_id,
                    RefreshSession.token_hash == token_hash(token),
                    RefreshSession.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
                .returning(RefreshSession.id)
            )
            if changed.scalar_one_or_none() is not None:
                db.add(SecurityAuditEvent(action="auth.logout", actor_user_id=user_id, session_id=session_id))
                await db.commit()
    _clear_refresh_cookie(response)
    response.status_code = 204
    return None


@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user
