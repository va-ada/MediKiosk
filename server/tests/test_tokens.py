from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.ids import today_ist
from app.models import Session as Visit
from app.models import Staff, Token

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


@pytest.fixture
def h(db: Session) -> dict[str, dict[str, str]]:
    rows = [
        Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", room="Room 1", pin_hash=hash_pin("1")),
        Staff(id="D2", name="Dr. Rao", role="doctor", department="general", room="Room 2", pin_hash=hash_pin("1")),
        Staff(id="N1", name="Nurse Asha", role="nurse", pin_hash=hash_pin("1")),
    ]
    db.add_all(rows)
    db.commit()
    return {s.id: {"Authorization": f"Bearer {create_jwt(s)}"} for s in rows}


def new_token(client: TestClient, code: str = "joint_pain") -> dict:
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    return client.post(
        f"/api/sessions/{sid}/triage", json={"complaint_code": code, "redflags": NO_FLAGS}, headers=K
    ).json()["token"]


def act(client: TestClient, tid: str, action: str, hdr: dict, body: dict | None = None):
    return client.post(f"/api/tokens/{tid}/{action}", json=body, headers=hdr)


def test_call_in_and_already_in(client: TestClient, h) -> None:
    t = new_token(client)
    called = act(client, t["id"], "call", h["D1"]).json()
    assert called["status"] == "called" and called["called_count"] == 1 and called["doctor_name"] == "Dr. Mehta"
    assert act(client, t["id"], "in", h["D1"]).json()["status"] == "in"
    assert act(client, t["id"], "in", h["D1"]).status_code == 200  # idempotent for the same doctor
    res = act(client, t["id"], "in", h["D2"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "already_in"
    assert act(client, t["id"], "call", h["N1"]).status_code == 403


def test_no_show_twice_then_reactivate(client: TestClient, h) -> None:
    t = new_token(client)
    act(client, t["id"], "call", h["D1"])
    first = act(client, t["id"], "no-show", h["D1"]).json()
    assert first["status"] == "waiting" and first["doctor_id"] is None
    act(client, t["id"], "call", h["D1"])
    assert act(client, t["id"], "no-show", h["D1"]).json()["status"] == "absent"
    res = act(client, t["id"], "reactivate", K)  # kiosk may reactivate (K or S)
    assert res.json()["status"] == "waiting"
    assert act(client, t["id"], "reactivate", K).json()["error"]["code"] == "invalid_state"


def test_outcome_out_closes_session(client: TestClient, db: Session, h) -> None:
    t = new_token(client)
    act(client, t["id"], "in", h["D1"])
    res = act(client, t["id"], "outcome", h["D1"], {"outcome": "out", "note": "ok"}).json()
    assert res["status"] == "done"
    visit = db.get(Visit, t["session_id"])
    db.refresh(visit)
    assert visit.status == "closed" and visit.closed_at is not None
    assert act(client, t["id"], "outcome", h["D1"], {"outcome": "out"}).json()["error"]["code"] == "invalid_state"


def test_recheck_same_day_and_signout(client: TestClient, h) -> None:
    t = new_token(client)
    act(client, t["id"], "in", h["D1"])
    res = act(client, t["id"], "outcome", h["D1"], {"outcome": "recheck", "note": "X-ray"}).json()
    assert (res["status"], res["lane"], res["preferred_doctor_id"]) == ("waiting", "priority", "D1")
    assert "recheck" in res["flags"]
    assert client.post("/api/doctors/signout", headers=h["D1"]).json() == {"returned_tokens": 1}
    assert client.get("/api/queue?department=ayurveda", headers=h["D1"]).json()[0]["preferred_doctor_id"] is None


def test_recheck_results_tomorrow(client: TestClient, db: Session, h) -> None:
    t = new_token(client)
    act(client, t["id"], "in", h["D1"])
    res = act(client, t["id"], "outcome", h["D1"], {"outcome": "recheck", "results_tomorrow": True}).json()
    assert res["status"] == "done"
    tomorrow = db.exec(select(Token).where(Token.session_id == t["session_id"], Token.id != t["id"])).one()
    assert tomorrow.day == today_ist() + timedelta(days=1)
    assert (tomorrow.lane, tomorrow.status, tomorrow.preferred_doctor_id) == ("priority", "waiting", "D1")
    assert client.get("/api/queue?department=ayurveda", headers=h["D1"]).json() == []  # not today


def test_refer_keeps_arrival_seq(client: TestClient, db: Session, h) -> None:
    t = new_token(client)
    act(client, t["id"], "in", h["D1"])
    res = act(client, t["id"], "outcome", h["D1"], {"outcome": "refer", "refer_department": "general"}).json()
    assert res["status"] == "referred"
    q = client.get("/api/queue?department=general", headers=h["D2"]).json()
    assert len(q) == 1 and q[0]["arrival_seq"] == t["arrival_seq"] and q[0]["lane"] == "priority"
    assert "referred" in q[0]["flags"]
    res = act(client, t["id"], "outcome", h["D1"], {"outcome": "refer"})
    assert res.json()["error"]["code"] in {"validation_error", "invalid_state"}


def test_followup_and_admit(client: TestClient, db: Session, h) -> None:
    t = new_token(client)
    act(client, t["id"], "in", h["D1"])
    assert (
        act(client, t["id"], "outcome", h["D1"], {"outcome": "followup"}).json()["error"]["code"] == "validation_error"
    )
    res = act(
        client, t["id"], "outcome", h["D1"], {"outcome": "followup", "followup_date": "2026-11-01", "admit": True}
    ).json()
    assert res["status"] == "done"
    row = db.get(Token, t["id"])
    db.refresh(row)
    assert row.followup_date == date(2026, 11, 1) and row.outcome_note.startswith("Admit: yes")
    assert audit.verify_chain(db)[0]
