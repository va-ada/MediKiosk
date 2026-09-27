import base64
import os

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.errors import ApiError
from app.models import AuditLog, PatientKey, Staff
from app.services import crypto
from app.services.files import load_file, store_file

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
PNG = b"\x89PNG\r\n\x1a\n" + b"fake image body" * 10


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "master_key_b64", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")
    monkeypatch.setattr(settings, "nlp_url", "http://nlp.test")


@pytest.fixture
def admins(db: Session) -> dict[str, dict[str, str]]:
    rows = [
        Staff(id="A1", name="Admin Priya", role="admin", pin_hash=hash_pin("5555")),
        Staff(id="A2", name="Admin Sunil", role="admin", pin_hash=hash_pin("6666")),
        Staff(id="D1", name="Dr. Mehta", role="doctor", pin_hash=hash_pin("1111")),
    ]
    db.add_all(rows)
    db.commit()
    return {s.id: {"Authorization": f"Bearer {create_jwt(s)}"} for s in rows}


def patient(client: TestClient) -> str:
    return client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]


def test_round_trip_and_ciphertext_on_disk(client: TestClient, db: Session, tmp_path) -> None:
    pid = patient(client)
    store_file(pid, "docs/a.bin", PNG)
    on_disk = (tmp_path / "patients" / pid / "docs" / "a.bin").read_bytes()
    assert not on_disk.startswith(b"\x89PNG") and b"fake image body" not in on_disk
    assert len(on_disk) == len(PNG) + 12 + 16  # nonce + GCM tag
    assert load_file(pid, "docs/a.bin") == PNG
    key = db.exec(select(PatientKey).where(PatientKey.patient_id == pid)).one()
    assert key.wrapped_key and key.destroyed_at is None
    store_file(pid, "docs/b.bin", b"second")
    assert len(db.exec(select(PatientKey)).all()) == 1  # one key per patient, reused


def test_tampering_and_path_swap_detected(client: TestClient, tmp_path) -> None:
    pid = patient(client)
    store_file(pid, "docs/a.bin", PNG)
    f = tmp_path / "patients" / pid / "docs" / "a.bin"
    blob = bytearray(f.read_bytes())
    blob[-1] ^= 1
    f.write_bytes(bytes(blob))
    with pytest.raises(ApiError) as e:
        load_file(pid, "docs/a.bin")
    assert e.value.code == "decrypt_failed"
    store_file(pid, "docs/c.bin", PNG)
    (tmp_path / "patients" / pid / "docs" / "d.bin").write_bytes(
        (tmp_path / "patients" / pid / "docs" / "c.bin").read_bytes()
    )
    with pytest.raises(ApiError):  # ciphertext is bound to its path (AAD)
        load_file(pid, "docs/d.bin")
    with pytest.raises(ValueError):
        store_file(pid, "../../escape.bin", b"x")


def test_erase_two_person_rule(client: TestClient, db: Session, admins) -> None:
    pid = patient(client)
    store_file(pid, "docs/a.bin", PNG)
    url = f"/api/admin/patients/{pid}/erase"
    res = client.post(url, json={"approver_staff_id": "A1", "approver_pin": "5555"}, headers=admins["A1"])
    assert res.status_code == 403  # same person can't approve their own erase
    res = client.post(url, json={"approver_staff_id": "A2", "approver_pin": "0000"}, headers=admins["A1"])
    assert res.status_code == 401 and res.json()["error"]["code"] == "invalid_pin"
    res = client.post(url, json={"approver_staff_id": "D1", "approver_pin": "1111"}, headers=admins["A1"])
    assert res.status_code == 403  # approver must be an admin
    assert (
        client.post(url, json={"approver_staff_id": "A2", "approver_pin": "6666"}, headers=admins["D1"]).status_code
        == 403
    )
    assert client.post(url, json={"approver_staff_id": "A2", "approver_pin": "6666"}, headers=admins["A1"]).json() == {
        "destroyed": True
    }
    key = db.exec(select(PatientKey).where(PatientKey.patient_id == pid)).one()
    db.refresh(key)
    assert key.wrapped_key is None and key.destroyed_at is not None
    for fn in (lambda: load_file(pid, "docs/a.bin"), lambda: store_file(pid, "docs/z.bin", b"x")):
        with pytest.raises(ApiError) as e:
            fn()
        assert e.value.status == 410 and e.value.code == "patient_erased"
    actions = [a.action for a in db.exec(select(AuditLog))]
    assert "patient.erase" in actions and "patient.erase_denied" in actions and audit.verify_chain(db)[0]


@respx.mock
def test_image_endpoint_410_after_erase(client: TestClient, db: Session, admins) -> None:
    respx.post("http://nlp.test/document").mock(
        return_value=httpx.Response(200, json={"doc_type": "unknown", "doc_date": None, "lines": [], "entities": []})
    )
    pid = patient(client)
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(
        f"/api/sessions/{sid}/consent",
        headers=K,
        json={"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True},
    )
    client.post(f"/api/sessions/{sid}/triage", json={"complaint_code": "fever", "redflags": NO_FLAGS}, headers=K)
    doc = client.post(
        f"/api/sessions/{sid}/documents", headers=K, data={"page_no": "1"}, files={"image": ("p.png", PNG, "image/png")}
    ).json()
    img = client.get(f"/api/documents/{doc['id']}/image", headers=admins["D1"])
    assert img.status_code == 200 and img.content == PNG
    client.post(
        f"/api/admin/patients/{pid}/erase",
        json={"approver_staff_id": "A2", "approver_pin": "6666"},
        headers=admins["A1"],
    )
    res = client.get(f"/api/documents/{doc['id']}/image", headers=admins["D1"])
    assert res.status_code == 410 and res.json()["error"]["code"] == "patient_erased"


def test_missing_master_key_is_explicit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    pid = patient(client)
    monkeypatch.setattr(settings, "master_key_b64", "")
    with pytest.raises(ApiError) as e:
        crypto.data_key(pid)
    assert e.value.code == "server_misconfigured"
