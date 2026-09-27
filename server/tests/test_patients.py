from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import AuditLog, Patient

K = {"X-Kiosk-Id": "KIOSK-01"}
KAMLA = "12345678901234"


def _register(client: TestClient, **kw) -> dict:
    body = {"name": "Sita Ram", "age": 45, "sex": "F", "language": "hi"} | kw
    return client.post("/api/patients/register", json=body, headers=K).json()


def test_register_sequential_ids(client: TestClient, db: Session) -> None:
    a = _register(client)
    b = _register(client, name="  Mohan   Lal ", sex="M", language="en")
    assert a["hospital_id"] == "MK-000001" and b["hospital_id"] == "MK-000002"
    assert b["name"] == "Mohan Lal" and b["abha_number"] is None and a["created_at"].endswith("Z")
    assert client.get(f"/api/patients/{a['id']}", headers=K).json() == a
    rows = db.exec(select(AuditLog)).all()
    assert [r.action for r in rows] == ["patient.create"] * 2 and rows[0].actor == "kiosk:KIOSK-01"
    assert audit.verify_chain(db)[0]


def test_register_validation(client: TestClient) -> None:
    for bad in ({"name": "   "}, {"age": 121}, {"age": -1}, {"sex": "X"}, {"language": "fr"}):
        res = client.post(
            "/api/patients/register", json={"name": "A", "age": 1, "sex": "M", "language": "hi"} | bad, headers=K
        )
        assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error", bad


def test_missing_kiosk_header(client: TestClient) -> None:
    res = client.post("/api/patients/register", json={"name": "A", "age": 1, "sex": "M", "language": "hi"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "missing_kiosk_id"
    assert client.get("/api/patients/x").json()["error"]["code"] == "missing_kiosk_id"


def test_aadhaar_like_field_never_stored(client: TestClient, db: Session) -> None:
    p = _register(client, aadhaar="123412341234", aadhaar_number="123412341234")
    assert "aadhaar" not in str(p)
    row = db.get(Patient, p["id"])
    assert "123412341234" not in str(row.model_dump())
    assert "123412341234" not in str([r.details for r in db.exec(select(AuditLog))])


def test_abha_found_creates_once(client: TestClient) -> None:
    body = {"abha_number": "12-3456-7890-1234", "otp": "123456"}
    first = client.post("/api/patients/abha/verify", json=body, headers=K).json()
    assert first["name"] == "Kamla Devi" and first["abha_number"] == KAMLA and first["language"] == "hi"
    again = client.post("/api/patients/abha/verify", json=body, headers=K).json()
    assert again["id"] == first["id"]


def test_abha_errors(client: TestClient) -> None:
    def post(abha: str, otp: str = "123456"):
        return client.post("/api/patients/abha/verify", json={"abha_number": abha, "otp": otp}, headers=K)

    assert post(KAMLA, "000000").status_code == 401 and post(KAMLA, "000000").json()["error"]["code"] == "invalid_otp"
    res = post("11112222333344")
    assert res.status_code == 404 and res.json()["error"]["code"] == "abha_not_found"
    for bad in ("123", "1234567890123a", "123456789012345"):
        res = post(bad)
        assert res.status_code == 422 and res.json()["error"]["code"] == "invalid_abha", bad


def test_get_unknown_patient(client: TestClient) -> None:
    res = client.get("/api/patients/nope", headers=K)
    assert res.status_code == 404 and res.json()["error"]["code"] == "not_found"
