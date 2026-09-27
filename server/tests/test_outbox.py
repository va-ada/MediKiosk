from datetime import timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.ids import utcnow
from app.models import Consent, Outbox, Patient, Setting, Staff
from app.models import Session as Visit
from app.services import outbox

HIS = "http://his.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "his_url", HIS)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


def row(db: Session, share: bool = True, revoked: bool = False) -> Outbox:
    p = Patient(hospital_id=f"MK-{utcnow().microsecond:06d}", name="P", age=40, sex="F", language="hi")
    db.add(p)
    db.flush()
    v = Visit(patient_id=p.id, kiosk_id="K", informant="self", status="closed", legal_basis="consent")
    db.add(v)
    db.flush()
    db.add(
        Consent(
            session_id=v.id,
            capture=True,
            scan=True,
            share_hospital=share,
            link_abha=False,
            check_passed=True,
            revoked_at=utcnow() if revoked else None,
        )
    )
    ob = Outbox(
        session_id=v.id,
        patient_id=p.id,
        payload={"resourceType": "Bundle", "entry": [{}, {}]},
        idempotency_key=f"{v.id}:v1",
        next_attempt_at=utcnow() - timedelta(seconds=1),
    )
    db.add(ob)
    db.commit()
    return ob


def set_island(db: Session, on: bool) -> None:
    db.merge(Setting(key="island_mode", value=on))
    db.commit()


@respx.mock
def test_sent_with_idempotency_key(db: Session) -> None:
    his = respx.post(f"{HIS}/fhir").mock(
        return_value=httpx.Response(200, json={"received": True, "id": "x", "duplicate": False})
    )
    ob = row(db)
    with httpx.Client() as c:
        assert outbox.drain_once(db, c) == {"sent": 1, "retry": 0, "skipped": 0}
    db.refresh(ob)
    assert ob.status == "sent" and ob.sent_at is not None
    assert his.calls.last.request.headers["Idempotency-Key"] == ob.idempotency_key
    with httpx.Client() as c:  # nothing left to do
        assert outbox.drain_once(db, c) == {"sent": 0, "retry": 0, "skipped": 0}
    assert audit.verify_chain(db)[0]


@respx.mock
def test_his_down_backoff(db: Session) -> None:
    respx.post(f"{HIS}/fhir").mock(side_effect=httpx.ConnectError("down"))
    ob = row(db)
    with httpx.Client() as c:
        outbox.drain_once(db, c)
        db.refresh(ob)
        assert (ob.status, ob.attempts) == ("pending", 1) and "ConnectError" in ob.last_error
        first_wait = ob.next_attempt_at
        assert outbox.drain_once(db, c)["retry"] == 0  # not due yet
        outbox.drain_once(db, c, now=utcnow() + timedelta(seconds=11))
        db.refresh(ob)
        assert ob.attempts == 2 and ob.next_attempt_at > first_wait
    assert [outbox.backoff(n).total_seconds() for n in (1, 2, 3, 6, 7, 20)] == [10, 20, 40, 300, 300, 300]


@respx.mock
def test_his_5xx_then_recovers(db: Session) -> None:
    route = respx.post(f"{HIS}/fhir")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json={"received": True, "id": "x", "duplicate": True}),
    ]
    ob = row(db)
    with httpx.Client() as c:
        outbox.drain_once(db, c)
        outbox.drain_once(db, c, now=utcnow() + timedelta(seconds=11))
    db.refresh(ob)
    assert ob.status == "sent" and ob.attempts == 1  # a repeat delivery (duplicate: true) is harmless


@respx.mock
def test_island_mode_sends_nothing(db: Session) -> None:
    his = respx.post(f"{HIS}/fhir").mock(return_value=httpx.Response(200, json={}))
    ob = row(db)
    set_island(db, True)
    with httpx.Client() as c:
        assert outbox.drain_once(db, c) == {"sent": 0, "retry": 0, "skipped": 0}
    assert not his.called
    set_island(db, False)
    with httpx.Client() as c:
        outbox.drain_once(db, c)
    db.refresh(ob)
    assert ob.status == "sent"


@respx.mock
@pytest.mark.parametrize(("share", "revoked"), [(False, False), (True, True)])
def test_consent_rechecked_at_send(db: Session, share: bool, revoked: bool) -> None:
    his = respx.post(f"{HIS}/fhir").mock(return_value=httpx.Response(200, json={}))
    ob = row(db, share=share, revoked=revoked)
    with httpx.Client() as c:
        assert outbox.drain_once(db, c)["skipped"] == 1
    db.refresh(ob)
    assert ob.status == "skipped_no_consent" and not his.called


def test_admin_routes(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "nlp_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "relay_url", "http://127.0.0.1:9")
    monkeypatch.setattr(settings, "ollama_url", "http://127.0.0.1:9")
    admin = Staff(id="A1", name="Admin", role="admin", pin_hash=hash_pin("1"))
    doc = Staff(id="D1", name="Doc", role="doctor", pin_hash=hash_pin("1"))
    db.add_all([admin, doc])
    db.commit()
    h = {"Authorization": f"Bearer {create_jwt(admin)}"}
    assert client.get("/api/admin/island", headers=h).json() == {"enabled": False}
    assert client.post("/api/admin/island", json={"enabled": True}, headers=h).json() == {"enabled": True}
    assert client.get("/api/admin/island", headers=h).json() == {"enabled": True}
    with respx.mock(assert_all_called=False) as m:
        m.get(f"{HIS}/bundles").mock(return_value=httpx.Response(200, json=[]))
        m.route(host="127.0.0.1").pass_through()
        health = client.get("/api/admin/health", headers=h).json()
    assert health == {"db": True, "nlp": False, "relay": False, "his": True, "ollama": False, "island_mode": True}
    row(db)
    items = client.get("/api/admin/outbox", headers=h).json()
    assert items[0]["resource_count"] == 2 and "payload" not in items[0]
    assert "payload" in client.get("/api/admin/outbox?include_payload=true", headers=h).json()[0]
    assert client.get("/api/admin/island", headers={"Authorization": f"Bearer {create_jwt(doc)}"}).status_code == 403
