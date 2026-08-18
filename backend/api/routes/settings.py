"""Settings API routes (read-only public settings, admin write)."""
from __future__ import annotations

from api.deps import get_current_active_user, require_role
from config import settings
from fastapi import APIRouter, Depends
from models.user import User
from pydantic import BaseModel

settings_router = APIRouter(prefix="/settings", tags=["settings"])


class PublicSettingsOut(BaseModel):
    llm_provider: str
    embed_model: str
    embed_dimension: int
    max_reference_upload_bytes: int
    access_token_expire_minutes: int
    refresh_token_expire_days: int


@settings_router.get("", response_model=PublicSettingsOut)
async def get_settings(_current_user: User = Depends(get_current_active_user)):
    return PublicSettingsOut(
        llm_provider=settings.llm_provider,
        embed_model=settings.embed_model,
        embed_dimension=settings.embed_dimension,
        max_reference_upload_bytes=settings.max_reference_upload_bytes,
        access_token_expire_minutes=settings.access_token_expire_minutes,
        refresh_token_expire_days=settings.refresh_token_expire_days,
    )


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None


@settings_router.put("", response_model=PublicSettingsOut)
async def update_settings(
    _payload: SettingsUpdate,
    _current_user: User = Depends(require_role("admin")),
):
    return PublicSettingsOut(
        llm_provider=settings.llm_provider,
        embed_model=settings.embed_model,
        embed_dimension=settings.embed_dimension,
        max_reference_upload_bytes=settings.max_reference_upload_bytes,
        access_token_expire_minutes=settings.access_token_expire_minutes,
        refresh_token_expire_days=settings.refresh_token_expire_days,
    )
