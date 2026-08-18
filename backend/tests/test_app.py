from app import app
from fastapi.testclient import TestClient


def test_health_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_app_has_routes():
    paths = set(app.openapi().get("paths", {}).keys())
    assert "/health" in paths
    assert "/devices" in paths
    assert "/rag/reference" in paths
