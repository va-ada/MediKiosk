from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth import create_jwt, hash_pin
from app.config import settings
from app.ids import today_ist, utcnow
from app.models import Patient, Staff, Token
from app.models import Session as Visit
from app.services import queue


@pytest.fixture(autouse=True)
def _secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")
    monkeypatch.setattr(settings, "wait_limit_min", 90)


@pytest.fixture
def staff(db: Session) -> dict[str, Staff]:
    rows = {
        "D1": Staff(
            id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", room="Room 1", pin_hash=hash_pin("1")
        ),
        "D2": Staff(
            id="D2", name="Dr. Rao", role="doctor", department="general", room="Room 2", pin_hash=hash_pin("1")
        ),
        "D3": Staff(
            id="D3", name="Dr. Iyer", role="doctor", department="ayurveda", room="Room 3", pin_hash=hash_pin("1")
        ),
        "N1": Staff(id="N1", name="Nurse Asha", role="nurse", pin_hash=hash_pin("1")),
    }
    db.add_all(rows.values())
    db.commit()
    return rows


def auth(s: Staff) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_jwt(s)}"}


_seq = iter(range(1, 1000))


def tok(
    db: Session,
    lane: str = "normal",
    dept: str = "ayurveda",
    age_min: int = 0,
    status: str = "waiting",
    preferred: str | None = None,
) -> Token:
    p = Patient(hospital_id=f"MK-{next(_seq):06d}", name="P", age=40, sex="F", language="hi")
    db.add(p)
    db.flush()
    v = Visit(patient_id=p.id, kiosk_id="K", informant="self", status="triaged", legal_basis="consent")
    db.add(v)
    db.flush()
    n = next(_seq)
    t = Token(
        display=f"A-{n:03d}",
        prefix="A",
        number=n,
        day=today_ist(),
        patient_id=p.id,
        session_id=v.id,
        department=dept,
        lane=lane,
        status=status,
        arrival_seq=n,
        preferred_doctor_id=preferred,
        created_at=utcnow() - timedelta(minutes=age_min),
    )
    db.add(t)
    db.commit()
    return t


def test_emergency_first(db: Session, staff) -> None:
    normal = tok(db, age_min=200)
    tok(db, "priority")
    emerg = tok(db, "emergency")
    assert queue.select_next(db, "ayurveda", "D1").id == emerg.id
    assert queue.preview(db, "ayurveda")[0].id == emerg.id
    assert queue.preview(db, "ayurveda")[-1].id == normal.id


def test_aged_normal_beats_priority(db: Session, staff) -> None:
    fresh = tok(db)
    prio = tok(db, "priority")
    assert queue.select_next(db, "ayurveda", "D1").id == prio.id
    aged = tok(db, age_min=95)
    assert queue.select_next(db, "ayurveda", "D1").id == aged.id
    assert fresh.id != aged.id


def test_priority_reserved_for_other_doctor_skipped(db: Session, staff) -> None:
    normal = tok(db)
    tok(db, "priority", preferred="D3")
    mine = tok(db, "priority", preferred="D1")
    assert queue.select_next(db, "ayurveda", "D1").id == mine.id
    mine.status = "done"
    db.add(mine)
    db.commit()
    assert queue.select_next(db, "ayurveda", "D1").id == normal.id


def test_departments_separate_and_empty(db: Session, staff) -> None:
    tok(db, dept="general")
    assert queue.select_next(db, "ayurveda", "D1") is None
    assert queue.select_next(db, "general", "D2") is not None


def test_routes_and_display(client: TestClient, db: Session, staff) -> None:
    a = tok(db, age_min=100)
    b = tok(db, "emergency")
    tok(db, dept="general")
    tok(db, status="done")
    res = client.get("/api/queue?department=ayurveda", headers=auth(staff["N1"])).json()
    assert [i["id"] for i in res] == [b.id, a.id]
    assert "aged" in res[1]["flags"] and res[1]["wait_min"] >= 100
    assert len(client.get("/api/queue", headers=auth(staff["D1"])).json()) == 2  # doctor's own department
    assert client.get("/api/queue").status_code == 401

    res = client.post("/api/queue/next", json={"department": "ayurveda"}, headers=auth(staff["D1"]))
    item = res.json()
    assert item["id"] == b.id and item["status"] == "called" and item["called_count"] == 1
    assert item["doctor_name"] == "Dr. Mehta"
    board = client.get("/api/queue?department=ayurveda", headers=auth(staff["D1"])).json()
    assert [i["id"] for i in board] == [a.id, b.id]  # waiting preview first, then called
    assert client.post("/api/queue/next", json={"department": "ayurveda"}, headers=auth(staff["N1"])).status_code == 403
    client.post("/api/queue/next", json={"department": "ayurveda"}, headers=auth(staff["D1"]))
    assert client.post("/api/queue/next", json={"department": "ayurveda"}, headers=auth(staff["D1"])).status_code == 204

    state = client.get("/api/display/state?department=ayurveda").json()
    assert set(state) == {"department", "now_serving", "next"}
    assert state["department"] == "ayurveda" and state["next"] == []
    assert [s["display"] for s in state["now_serving"]] == [a.display, b.display]
    assert set(state["now_serving"][0]) == {"display", "doctor_name", "room", "called_at"}
    assert state["now_serving"][0]["room"] == "Room 1"
    general = client.get("/api/display/state?department=general").json()
    assert len(general["next"]) == 1 and general["now_serving"] == []
