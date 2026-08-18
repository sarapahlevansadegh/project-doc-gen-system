
from core.security import create_access_token, create_refresh_token, verify_password
from models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def build_tokens(user_id: str, role: str) -> dict:
    access = create_access_token({"sub": str(user_id), "role": role})
    refresh = create_refresh_token({"sub": str(user_id), "role": role})
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }
