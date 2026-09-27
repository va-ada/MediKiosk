import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.ids import utcnow
from app.models import Alert, Staff, Token
from app.services import escalation

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


@pytest.fixture
def h(db: Session) -> dict[str, dict[str, str]]:
    rows = [
        Staff(id="N1", name="Nurse Asha", role="nurse", pin_hash=hash_pin("1")),
        Staff(id="K1", name="Desk Ravi", role="desk", pin_hash=hash_pin("1")),
    ]
    db.add_all(rows)
    db.commit()
    return {s.id: {"Authorization": f"Bearer {create_jwt(s)}"} for s in rows}


def triaged(client: TestClient, flags: dict = NO_FLAGS) -> dict:
    pid = client.post(
        "/api/patients/register", json={"name": "Ram", "age": 70, "sex": "M", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    return client.post(
        f"/api/sessions/{sid}/triage", json={"complaint_code": "fever", "redflags": flags}, headers=K
    ).json()


def press(client: TestClient, alert_id: str, session_id: str | None = None, reason: str = "chest_pain"):
    return client.post(
        "/api/alerts/emergency",
        headers=K,
        json={"id": alert_id, "kiosk_id": "KIOSK-01", "reason_code": reason, "session_id": session_id},
    )


def test_emergency_idempotent(client: TestClient, db: Session) -> None:
    aid = str(uuid.uuid4())
    first = press(client, aid).json()
    again = press(client, aid).json()
    assert first == again and first["reason_text"] == "Emergency button: chest pain"
    assert (first["level"], first["source"], first["status"]) == ("emergency", "button", "open")
    assert len(db.exec(select(Alert)).all()) == 1
    # unknown session never blocks an emergency
    assert press(client, str(uuid.uuid4()), session_id="nope").json()["session_id"] is None
    assert audit.verify_chain(db)[0]


def test_list_ack_and_roles(client: TestClient, h) -> None:
    aid = str(uuid.uuid4())
    press(client, aid)
    assert client.get("/api/alerts", headers=h["K1"]).status_code == 403
    assert client.get("/api/alerts").status_code == 401
    assert [a["id"] for a in client.get("/api/alerts?status=open,acknowledged", headers=h["N1"]).json()] == [aid]
    acked = client.post(f"/api/alerts/{aid}/ack", headers=h["N1"]).json()
    assert acked["status"] == "acknowledged" and acked["acknowledged_by"] == "N1"
    assert client.get("/api/alerts?status=open", headers=h["N1"]).json() == []
    assert client.get("/api/alerts?status=bogus", headers=h["N1"]).json()["error"]["code"] == "validation_error"


def test_confirmed_moves_lane_to_emergency(client: TestClient, db: Session, h) -> None:
    t = triaged(client)
    aid = str(uuid.uuid4())
    press(client, aid, session_id=t["session"]["id"])
    res = client.post(f"/api/alerts/{aid}/resolve", json={"outcome": "confirmed"}, headers=h["N1"]).json()
    assert res["status"] == "confirmed" and res["resolved_by"] == "N1"
    assert db.get(Token, t["token"]["id"]).lane == "emergency"
    again = client.post(f"/api/alerts/{aid}/resolve", json={"outcome": "downgraded"}, headers=h["N1"])
    assert again.json()["error"]["code"] == "invalid_state"


def test_downgraded_keeps_arrival_seq(client: TestClient, db: Session, h) -> None:
    t = triaged(client, NO_FLAGS | {"chest_pain": True, "breathless": True})
    alert = t["alerts"][0]
    token = db.get(Token, t["token"]["id"])
    token.lane = "emergency"
    db.add(token)
    db.commit()
    client.post(f"/api/alerts/{alert['id']}/ack", headers=h["N1"])
    res = client.post(f"/api/alerts/{alert['id']}/resolve", json={"outcome": "downgraded"}, headers=h["N1"]).json()
    assert res["status"] == "downgraded"
    db.refresh(token)
    assert token.lane == "normal" and token.arrival_seq == t["token"]["arrival_seq"]


def test_escalation(db: Session, client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "escalate_after_sec", 60)
    old, fresh = str(uuid.uuid4()), str(uuid.uuid4())
    press(client, old)
    press(client, fresh)
    row = db.get(Alert, old)
    row.created_at = utcnow() - timedelta(seconds=61)
    db.add(row)
    db.commit()
    assert [p["id"] for p in escalation.escalate_once(db)] == [old]
    assert escalation.escalate_once(db) == []  # already escalated
    db.refresh(row)
    assert row.escalated is True and db.get(Alert, fresh).escalated is False
