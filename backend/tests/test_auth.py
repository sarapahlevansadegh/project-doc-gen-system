"""Authentication and authorization tests (Milestone 9.2).

Uses the shared `client`/`db_session` fixtures from conftest.py - each
test runs inside its own rolled-back transaction, so e.g.
test_register_creates_user can rely on being the *actual* first user in
the database (triggering the "first user becomes admin, no auth
required" bootstrap in api/routes/auth.py's register()) regardless of
what earlier tests or earlier pytest runs did.
"""
from __future__ import annotations

import uuid

from core.security import hash_password
from models.user import User
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_user(
    db_session: AsyncSession,
    email: str,
    password: str,
    role: str = "viewer",
    active: bool = True,
) -> None:
    db_session.add(
        User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=hash_password(password),
            full_name=email.split("@")[0],
            role=role,
            is_active=active,
        )
    )
    await db_session.commit()


async def test_register_creates_user(client):
    payload = {
        "email": "test@example.com",
        "password": "secure123",
        "full_name": "Test User",
        "role": "viewer",
    }
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == payload["email"]
    
    # First user in an empty DB always becomes admin (bootstrap logic in
    # api/routes/auth.py's register()), regardless of the requested role.
    assert body["role"] == "admin"
    assert "id" in body


async def test_register_duplicate_email_returns_409(client):
    payload = {
        "email": "dup@example.com",
        "password": "secure123",
        "full_name": "Dup User",
    }
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    # api/routes/auth.py raises 409 (Conflict) for a true duplicate email,
    # not 400 - the previous assertion here was stale relative to the
    # endpoint's actual status code, unrelated to the DB-isolation fix.
    assert resp.status_code == 409
    assert "already registered" in resp.json()["detail"].lower()


async def test_login_returns_tokens(client):
    await client.post(
        "/auth/register", json={"email": "login@example.com", "password": "secure123"}
    )
    resp = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "secure123"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_invalid_credentials_returns_401(client):
    resp = await client.post("/auth/login", json={"email": "no@example.com", "password": "wrong"})
    assert resp.status_code == 401
    assert "invalid credentials" in resp.json()["detail"].lower()


async def test_get_me_without_token_returns_401(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_get_me_with_valid_token_returns_user(client):
    await client.post("/auth/register", json={"email": "me@example.com", "password": "secure123"})
    login = (
        await client.post(
            "/auth/login", json={"email": "me@example.com", "password": "secure123"}
        )
    ).json()
    token = login["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "me@example.com"


async def test_inactive_user_cannot_login(client, db_session):
    await _seed_user(db_session, "inactive@example.com", "secure123", active=False)
    resp = await client.post(
        "/auth/login", json={"email": "inactive@example.com", "password": "secure123"}
    )
    assert resp.status_code == 403
    assert "inactive" in resp.json()["detail"].lower()


async def test_protected_devices_requires_auth(client):
    resp = await client.get("/devices")
    assert resp.status_code == 401
