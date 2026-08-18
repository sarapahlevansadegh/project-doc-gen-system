from config import settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_sessionmaker = None


def _build_engine():
    """Lazily build the async engine so importing this module does not
    require a reachable Postgres database (useful for tests/imports)."""
    global _engine, _sessionmaker
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
    return _engine


def AsyncSessionLocal():
    """Return a new async session. Builds the engine lazily on first call."""
    _build_engine()
    return _sessionmaker()


def get_engine():
    """Return the lazily-built async engine."""
    return _build_engine()
