"""FastAPI application entry point."""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from api.routes import api_router
from config import settings
from core.database import get_engine
from core.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

try:
    from scalar_fastapi import get_scalar_api_reference
except ImportError:
    get_scalar_api_reference = None


def _get_app_version() -> str:
    try:
        return _pkg_version("doc-gen-system")
    except PackageNotFoundError:
        return "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    yield
    await engine.dispose()


app = FastAPI(
    title="DocGen API",
    description="Medical device software documentation generation system. "
    "Generates IEC 62304-compliant Software Architectural Design documents "
    "from device specifications using LLM and RAG.",
    version=_get_app_version(),
    lifespan=lifespan,
    redirect_slashes=False,
    contact={
        "name": "DocGen Team",
        "url": "https://github.com/your-org/doc-gen-system",
    },
    license_info={
        "name": "Proprietary",
    },
)

# --- Middleware (order matters: outermost first) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware, logger=logger)
app.add_middleware(RequestIDMiddleware)

# --- Rate limiting (optional) ---
if settings.rate_limit_enabled:
    try:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address

        limiter = Limiter(key_func=get_remote_address)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
        logger.info("Rate limiting enabled: %s req/%ss", settings.rate_limit_requests, settings.rate_limit_window_seconds)
    except ImportError:
        logger.warning("slowapi not installed; rate limiting disabled")


# --- Routes ---
app.include_router(api_router)


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    rid = getattr(request.state, "request_id", "-")
    logger.error("Unhandled exception [%s] %s: %s", rid, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": rid},
    )


# --- Scalar API docs ---
@app.get("/scalar", include_in_schema=False)
async def scalar():
    if get_scalar_api_reference is None:
        return {"detail": "Scalar documentation UI is not installed"}
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        title=app.title,
    )
