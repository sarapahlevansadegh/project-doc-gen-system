"""Health check endpoint with depth."""
from __future__ import annotations

from api.deps import get_db
from fastapi import APIRouter
from sqlalchemy import text

health_router = APIRouter(tags=["health"])


@health_router.get("/health")
async def health():
    return {"status": "ok"}


@health_router.get("/health/ready")
async def health_ready():
    """Deep health check: verifies database connectivity."""
    db_gen = get_db()
    db = await db_gen.__anext__()
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        return {"status": "degraded", "database": str(exc)}
    finally:
        await db_gen.aclose()
