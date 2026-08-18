"""Authentication and authorization tests (Milestone 9.2)."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from core.database import AsyncSessionLocal, get_engine
from models.user import User
from services.auth import hash_password
from sqlalchemy import text


@pytest.fixture
def _client():
    try:
        from app import app
        from fastapi.testclient import TestClient
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    with TestClient(app) as c:
        yield c


def _db_available() -> bool:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _ok():
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))

        try:
            loop.run_until_complete(_ok())
        finally:
            try:
                loop.run_until_complete(get_engine().dispose())
            except Exception:
                pass
            loop.close()
        return True
    except Exception as exc:
        if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
            return False
        raise


@pytest.fixture(autouse=True)
def _skip_if_no_db():
    if not _db_available():
        pytest.skip("Postgres unavailable")


def _seed_user(email: str, password: str, role: str = "viewer", active: bool = True):
    loop = asyncio.new_event_loop()
    try:
        async def _seed():
            async with AsyncSessionLocal() as db:
                db.add(
                    User(
                        id=uuid.uuid4(),
                        email=email,
                        hashed_password=hash_password(password),
                        full_name=email.split("@")[0],
                        role=role,
                        is_active=active,
                    )
                )
                await db.commit()
        loop.run_until_complete(_seed())
    finally:
        try:
            loop.run_until_complete(get_engine().dispose())
        except Exception:
            pass
        loop.close()


def test_register_creates_user(_client):
    payload = {
        "email": "test@example.com",
        "password": "secure123",
        "full_name": "Test User",
        "role": "viewer",
    }
    resp = _client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == payload["email"]
    assert body["role"] == "viewer"
    assert "id" in body


def test_register_duplicate_email_returns_400(_client):
    payload = {
        "email": "dup@example.com",
        "password": "secure123",
        "full_name": "Dup User",
    }
    _client.post("/auth/register", json=payload)
    resp = _client.post("/auth/register", json=payload)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"].lower()


def test_login_returns_tokens(_client):
    _client.post("/auth/register", json={"email": "login@example.com", "password": "secure123"})
    resp = _client.post("/auth/login", json={"email": "login@example.com", "password": "secure123"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


def test_login_invalid_credentials_returns_401(_client):
    resp = _client.post("/auth/login", json={"email": "no@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert "invalid credentials" in resp.json()["detail"].lower()


def test_get_me_without_token_returns_401(_client):
    resp = _client.get("/auth/me")
    assert resp.status_code == 401


def test_get_me_with_valid_token_returns_user(_client):
    _client.post("/auth/register", json={"email": "me@example.com", "password": "secure123"})
    login = _client.post("/auth/login", json={"email": "me@example.com", "password": "secure123"}).json()
    token = login["access_token"]
    resp = _client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "me@example.com"


def test_inactive_user_cannot_login(_client):
    _seed_user("inactive@example.com", "secure123", active=False)
    resp = _client.post("/auth/login", json={"email": "inactive@example.com", "password": "secure123"})
    assert resp.status_code == 403
    assert "inactive" in resp.json()["detail"].lower()


def test_protected_devices_requires_auth(_client):
    resp = _client.get("/devices")
    assert resp.status_code == 401
