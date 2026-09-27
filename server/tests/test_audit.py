from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app import audit


def _three(db: Session) -> None:
    audit.record(db, "system", "patient.create", "patient", "p1", {"name": "कमला"})
    audit.record(db, "kiosk:KIOSK-01", "session.create", "session", "s1", {"informant": "self"})
    audit.record(db, "staff:D1", "fact.verify", "fact", "f1", {"action": "approve", "n": 1.5})
    db.commit()


def test_empty_chain_is_valid(db: Session) -> None:
    assert audit.verify_chain(db) == (True, 0, None)


def test_three_records_valid_and_linked(db: Session) -> None:
    _three(db)
    assert audit.verify_chain(db) == (True, 3, None)
    rows = [audit.to_dict(r) for r in db.exec(audit.select(audit.AuditLog).order_by(audit.AuditLog.id))]
    assert rows[0]["prev_hash"] == "0" * 64
    assert rows[1]["prev_hash"] == rows[0]["hash"]
    assert rows[0]["ts"].endswith("Z")


def test_tampered_details_breaks_chain_at_row_2(db: Session) -> None:
    _three(db)
    db.exec(text('UPDATE audit_log SET details = \'{"informant": "proxy"}\' WHERE id = 2'))
    db.commit()
    db.expire_all()
    assert audit.verify_chain(db) == (False, 2, 2)


def test_routes(client: TestClient, db: Session) -> None:
    assert client.get("/api/admin/audit/verify").json() == {"valid": True, "checked": 0, "first_bad_id": None}
    _three(db)
    listed = client.get("/api/admin/audit?limit=2").json()
    assert [r["id"] for r in listed] == [3, 2]
    assert client.get("/api/admin/audit/verify").json() == {"valid": True, "checked": 3, "first_bad_id": None}
