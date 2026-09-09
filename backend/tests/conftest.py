"""Shared test fixtures for backend/tests.

`db_session` gives each test its own SQLAlchemy async session bound to a
connection-level transaction with a SAVEPOINT
(`join_transaction_mode="create_savepoint"`), rolled back after the test -
so nothing a test commits (users, devices, etc.) is ever visible to a
later test, or to a later `pytest` invocation. This is what
test_register_creates_user (and friends) need to reliably be treated as
the *actual* first user in the DB, which is what triggers the
"first user becomes admin, no auth required" bootstrap in
api/routes/auth.py's register() - without it, any admin user left behind
by an earlier test run changes that path for every test after it.

`client` is an httpx.AsyncClient wired directly to the FastAPI app via
ASGITransport and app.dependency_overrides[get_db], sharing the *same*
event loop pytest-asyncio already manages for the test (asyncio_mode is
"auto" - see pyproject.toml). This is deliberately not Starlette's
synchronous TestClient: TestClient runs the app in its own background
thread with its own event loop, and handing it a pre-built AsyncSession
created under pytest-asyncio's loop is exactly what produced the
"attached to a different loop" RuntimeErrors seen in
test_chunk_service.py and test_auth.py::test_inactive_user_cannot_login.
Every request a test makes (register, login, create device, etc.) runs
inside that test's own transaction and is rolled back with it.

`_SerializedSession` exists because of a second, distinct bug found while
debugging test_register_duplicate_email_returns_409: api/deps.py's
register() has two sibling dependencies that both resolve `get_db`
(directly, and nested inside get_optional_current_active_user).
FastAPI/Starlette resolves sibling dependencies concurrently via
anyio.create_task_group, and its dependency cache doesn't atomically
guard against both branches entering get_db() before either result is
cached. In production this is harmless - every get_db() call builds an
independent AsyncSessionLocal()/connection from the pool. Here, where
every call to the override must yield the *same* shared db_session so
SAVEPOINT rollback isolation works, that harmless double-call becomes two
concurrent operations on one asyncpg connection -> "InterfaceError:
cannot perform operation: another operation is in progress", which then
poisons that connection for every subsequent test in the run (each
failure traceback shows the identical connection object id). The lock is
held only for the duration of each individual call, never across the
generator's whole yield - holding it across the whole yield deadlocks,
since the outer dependency stays open for the entire request while the
nested one needs the same lock to resolve first.

One-time cleanup note: this fixture only guarantees isolation for tests
that use it. Rows committed by earlier ad-hoc test runs (before this
conftest existed) are still sitting in the real database and will still
affect the "first user" bootstrap check until they're cleared out once,
e.g. `TRUNCATE users CASCADE;`.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from api.deps import get_db
from core.database import get_engine
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


class _SerializedSession:
    """Duck-typed AsyncSession wrapper: serializes calls that touch the
    DBAPI connection, passes everything else straight through. See
    module docstring for why this is needed."""

    def __init__(self, session: AsyncSession, lock: asyncio.Lock) -> None:
        self._session = session
        self._lock = lock

    async def execute(self, *args, **kwargs):
        async with self._lock:
            return await self._session.execute(*args, **kwargs)

    async def scalar(self, *args, **kwargs):
        async with self._lock:
            return await self._session.scalar(*args, **kwargs)

    async def scalars(self, *args, **kwargs):
        async with self._lock:
            return await self._session.scalars(*args, **kwargs)

    async def commit(self):
        async with self._lock:
            return await self._session.commit()

    async def rollback(self):
        async with self._lock:
            return await self._session.rollback()

    async def flush(self, *args, **kwargs):
        async with self._lock:
            return await self._session.flush(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        async with self._lock:
            return await self._session.refresh(*args, **kwargs)

    async def close(self):
        # db_session fixture owns the real lifecycle; don't close here.
        return None

    def add(self, *args, **kwargs):
        return self._session.add(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._session, name)


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = get_engine()
    try:
        connection = await engine.connect()
    except (OperationalError, OSError) as exc:
        pytest.skip(f"Postgres unavailable: {exc}")

    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )

    try:
        yield session
    finally:
        await session.close()
        try:
            await transaction.rollback()
        except Exception:
            pass
        try:
            await connection.close()
        except Exception:
            await connection.invalidate()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    from app import app

    lock = asyncio.Lock()

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield _SerializedSession(db_session, lock)  # type: ignore[misc]

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
