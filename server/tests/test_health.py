from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    client = TestClient(app)
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "version": "0.1.0"}


def test_unknown_route_uses_error_body() -> None:
    res = TestClient(app).get("/api/nope")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "not_found"
