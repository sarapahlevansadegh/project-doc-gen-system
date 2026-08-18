"""Authentication and user bootstrap routes."""
from __future__ import annotations

from api.deps import get_current_active_user, get_db, get_optional_current_active_user
from core.security import decode_token, hash_password, verify_password
from fastapi import APIRouter, Depends, HTTPException
from models.user import User
from schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut
from services.auth import build_tokens
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

auth_router = APIRouter(tags=["auth"])


@auth_router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    email = str(payload.email).lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    return TokenResponse(**build_tokens(str(user.id), user.role))


@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        payload_data = decode_token(payload.refresh_token)
        if payload_data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload_data.get("sub")
        payload_data.get("role", "viewer")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return TokenResponse(**build_tokens(str(user.id), user.role))


@auth_router.post("/register", response_model=UserOut, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_active_user),
):
    """Create the initial admin, then require an admin for all later users."""
    email = str(payload.email).lower()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user_count = await db.scalar(select(func.count()).select_from(User))
    is_initial_user = user_count == 0
    if is_initial_user:
        role = "admin"
    else:
        if current_user is None or current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only an administrator can create additional users",
            )
        role = payload.role

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    await db.refresh(user)
    return user


@auth_router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user
