from __future__ import annotations

import asyncio

from config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker = None
_engine_loop: asyncio.AbstractEventLoop | None = None


def _build_engine():
    """Lazily build the async engine, rebuilding it if the running event
    loop has changed since it was last built.

    SQLAlchemy's async connection pool lazily creates an internal
    asyncio.Queue the first time it's used, bound to whatever loop is
    running at that moment. Calling engine.dispose() closes the pooled
    connections but does NOT reset that loop binding - reusing the same
    engine object across genuinely different loops (pytest-asyncio's
    session loop vs. a test's own asyncio.new_event_loop(), vs.
    TestClient's own portal loop - this project's test suite legitimately
    uses all three) then raises opaque "Task ... pending" /
    "attached to a different loop" RuntimeErrors no matter how carefully
    dispose() is called beforehand. Detecting the mismatch here and
    transparently dropping/rebuilding fixes it regardless of call order;
    the old engine's connections are simply abandoned (best effort - there
    is no loop left that could safely await closing them) rather than
    disposed, which is a non-issue in tests/dev and is the standard
    trade-off for engines that must be usable from more than one loop over
    a process's lifetime.
    """
    global _engine, _sessionmaker, _engine_loop
    try:
        current_loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _engine is not None and current_loop is not None and _engine_loop is not current_loop:
        _engine = None
        _sessionmaker = None

    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
        )
        _sessionmaker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        _engine_loop = current_loop
    return _engine


def AsyncSessionLocal():
    """Return a new async session. Builds the engine lazily on first call."""
    _build_engine()
    return _sessionmaker()


def get_engine():
    """Return the lazily-built async engine."""
    return _build_engine()
