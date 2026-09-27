"""S19: every route enforces its §4 auth marker. Walks the real route table, so new routes can't skip auth."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

PUBLIC = {("GET", "/api/health"), ("POST", "/api/staff/login"), ("GET", "/api/display/state")}
KIOSK_ONLY = {  # K routes: staff tokens don't replace the kiosk header
    ("POST", "/api/patients/register"),
    ("POST", "/api/patients/abha/verify"),
    ("POST", "/api/sessions"),
    ("POST", "/api/sessions/{session_id}/consent"),
    ("POST", "/api/sessions/{session_id}/triage"),
    ("GET", "/api/sessions/{session_id}/next-question"),
    ("POST", "/api/sessions/{session_id}/answers"),
    ("POST", "/api/sessions/{session_id}/answers/audio"),
    ("POST", "/api/sessions/{session_id}/documents"),
    ("GET", "/api/sessions/{session_id}/readback"),
    ("POST", "/api/sessions/{session_id}/readback"),
    ("POST", "/api/sessions/{session_id}/submit"),
    ("POST", "/api/alerts/emergency"),
}
KIOSK_OR_STAFF = {
    ("GET", "/api/patients/{patient_id}"),
    ("GET", "/api/sessions/{session_id}"),
    ("GET", "/api/documents/{doc_id}"),
    ("POST", "/api/tokens/{token_id}/reactivate"),
}
ROLES = {  # S:role routes (§4) → allowed roles
    r"^/api/queue": {"doctor", "nurse"},
    r"^/api/queue/next$": {"doctor"},
    r"^/api/tokens/[^/]+/(call|in|no-show|outcome)$": {"doctor"},
    r"^/api/doctors/signout$": {"doctor"},
    r"^/api/sessions/[^/]+/(summary|sections/.+|ayush-exam|diagnosis)$": {"doctor"},
    r"^/api/facts/": {"doctor"},
    r"^/api/alerts(/[^/]+/(ack|resolve))?$": {"nurse", "doctor"},
    r"^/api/admin/": {"admin"},
    r"^/api/terminology/": {"doctor"},
    r"^/api/documents/[^/]+/image$": {"doctor", "nurse", "desk", "admin"},
}


def api_routes() -> list[tuple[str, str]]:
    """Every HTTP route under /api, from the OpenAPI schema (FastAPI keeps included routers nested)."""
    out = [
        (m.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        if path.startswith("/api/")
        for m in ops
        if m in {"get", "post", "put", "patch", "delete"}
    ]
    assert len(out) > 40, f"only {len(out)} routes collected — route discovery is broken"
    return sorted(out)


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path).replace("sections/x/", "sections/hpi/")


def roles_for(path: str) -> set[str] | None:
    found = None
    for pattern, roles in ROLES.items():  # last (most specific) match wins
        if re.search(pattern, path):
            found = roles
    return found


def test_every_route_is_classified() -> None:
    for method, path in api_routes():
        known = (method, path) in PUBLIC | KIOSK_ONLY | KIOSK_OR_STAFF or roles_for(concrete(path)) is not None
        assert known, f"{method} {path} has no auth classification — add it to test_auth_guards.py"


@pytest.mark.parametrize(("method", "path"), api_routes())
def test_anonymous_is_rejected(client: TestClient, method: str, path: str) -> None:
    if (method, path) in PUBLIC:
        return
    res = client.request(method, concrete(path), json={})
    assert res.status_code in (400, 401), (method, path, res.status_code, res.text[:120])
    assert res.json()["error"]["code"] in ("missing_kiosk_id", "unauthorized")


@pytest.mark.parametrize(("method", "path"), api_routes())
def test_wrong_role_is_forbidden(client: TestClient, staff_headers, method: str, path: str) -> None:
    allowed = roles_for(concrete(path))
    if allowed is None or (method, path) in KIOSK_OR_STAFF:
        return
    for role in {"doctor", "nurse", "desk", "admin"} - allowed:
        res = client.request(method, concrete(path), json={}, headers=staff_headers(role))
        assert res.status_code == 403 and res.json()["error"]["code"] == "forbidden", (method, path, role)


def test_public_routes_and_kiosk_header(client: TestClient, kiosk_headers) -> None:
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/display/state").status_code == 200
    assert client.get("/api/queue").status_code == 401  # card acceptance: no token → 401
    assert client.get("/api/sessions/x", headers=kiosk_headers).status_code == 404  # header accepted, then 404
