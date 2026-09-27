from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import AuditLog

K = {"X-Kiosk-Id": "KIOSK-01"}
ALL_ON = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}


def _patient(client: TestClient) -> str:
    body = {"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}
    return client.post("/api/patients/register", json=body, headers=K).json()["id"]


def test_create_consent_flow(client: TestClient, db: Session) -> None:
    pid = _patient(client)
    s = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()
    assert s["status"] == "identifying" and s["kiosk_id"] == "KIOSK-01" and s["legal_basis"] == "consent"
    assert s["informant_relation"] is None and s["created_at"].endswith("Z") and s["submitted_at"] is None

    c = client.post(f"/api/sessions/{s['id']}/consent", json=ALL_ON, headers=K).json()
    assert c["session_id"] == s["id"] and c["share_hospital"] is True and c["revoked_at"] is None
    assert client.get(f"/api/sessions/{s['id']}", headers=K).json()["status"] == "consented"

    actions = [r.action for r in db.exec(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["patient.create", "session.create", "consent.create"]
    assert audit.verify_chain(db)[0]


def test_proxy_relation(client: TestClient) -> None:
    pid = _patient(client)
    s = client.post(
        "/api/sessions", json={"patient_id": pid, "informant": "proxy", "informant_relation": " son "}, headers=K
    ).json()
    assert s["informant"] == "proxy" and s["informant_relation"] == "son"
    s = client.post(
        "/api/sessions", json={"patient_id": pid, "informant": "self", "informant_relation": "son"}, headers=K
    ).json()
    assert s["informant_relation"] is None


def test_errors(client: TestClient) -> None:
    res = client.post("/api/sessions", json={"patient_id": "nope", "informant": "self"}, headers=K)
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
    assert client.get("/api/sessions/nope", headers=K).status_code == 404
    assert client.post("/api/sessions/nope/consent", json=ALL_ON, headers=K).status_code == 404
    pid = _patient(client)
    res = client.post("/api/sessions", json={"patient_id": pid, "informant": "friend"}, headers=K)
    assert res.json()["error"]["code"] == "validation_error"
    res = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"})
    assert res.json()["error"]["code"] == "missing_kiosk_id"
