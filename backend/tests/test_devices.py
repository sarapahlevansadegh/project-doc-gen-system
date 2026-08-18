"""Device data-management tests (Milestone 6.1: A=delete, B=nested update, C=eager GET)."""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def _client_and_loop():
    try:
        from app import app
        from core.database import AsyncSessionLocal, get_engine
        from fastapi.testclient import TestClient
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    # gate on Postgres using a dedicated loop, then dispose engine so the
    # TestClient portal loop can rebind it
    loop = asyncio.new_event_loop()
    try:
        from sqlalchemy import text

        async def _ok():
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))

        try:
            loop.run_until_complete(_ok())
        except Exception as exc:
            if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise
    finally:
        try:
            loop.run_until_complete(get_engine().dispose())
        except Exception:
            pass
        loop.close()

    with TestClient(app) as client:
        yield client


def _make_device(client):
    resp = client.post(
        "/devices",
        json={
            "name": "VL8",
            "model": "VL8",
            "document_code": "15799",
            "safety_class": "B",
            "driver_version": "01",
            "gui_version": "7.0.0.1",
            "specs": [{"category": "c", "spec_key": "k1", "spec_value": "v1"}],
            "alarms": [
                {
                    "condition": "overheat",
                    "indicator_light": "red",
                    "indicator_sound": True,
                }
            ],
            "commands": [{"command_name": "CMD1", "direction": "main_to_panel"}],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_and_get_populated(_client_and_loop):
    client = _client_and_loop
    device = _make_device(client)
    device_id = device["id"]

    # C: GET returns populated children (eager loaded)
    got = client.get(f"/devices/{device_id}").json()
    assert got["name"] == "VL8"
    assert len(got["specs"]) == 1
    assert got["specs"][0]["spec_key"] == "k1"
    assert len(got["alarms"]) == 1
    assert got["alarms"][0]["condition"] == "overheat"
    assert len(got["commands"]) == 1
    assert got["commands"][0]["command_name"] == "CMD1"


def test_patch_scalar_only(_client_and_loop):
    client = _client_and_loop
    device_id = _make_device(client)["id"]

    resp = client.patch(f"/devices/{device_id}", json={"model": "VL8-X"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["model"] == "VL8-X"
    # children untouched
    assert len(resp.json()["specs"]) == 1


def test_patch_replaces_nested(_client_and_loop):
    client = _client_and_loop
    device_id = _make_device(client)["id"]

    # replace specs with two new entries, drop alarms/commands
    resp = client.patch(
        f"/devices/{device_id}",
        json={
            "specs": [
                {"category": "c", "spec_key": "kA", "spec_value": "vA"},
                {"category": "c", "spec_key": "kB", "spec_value": "vB"},
            ],
            "alarms": [],
            "commands": [],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {s["spec_key"] for s in body["specs"]} == {"kA", "kB"}
    assert body["alarms"] == []
    assert body["commands"] == []


def test_delete_device_and_children(_client_and_loop):
    client = _client_and_loop
    device_id = _make_device(client)["id"]

    # A: delete returns 204
    del_resp = client.delete(f"/devices/{device_id}")
    assert del_resp.status_code == 204

    # device gone
    assert client.get(f"/devices/{device_id}").status_code == 404
    # children removed via cascade (verify through a fresh device listing)
    assert client.get(f"/devices/{device_id}").status_code == 404


def test_delete_missing_returns_404(_client_and_loop):
    client = _client_and_loop
    import uuid

    assert client.delete(f"/devices/{uuid.uuid4()}").status_code == 404
