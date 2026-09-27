import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.models import Document, Fact, Staff

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
NLP = "http://nlp.test"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
OCR = {
    "doc_type": "lab_report",
    "doc_date": "2026-08-12",
    "lines": [{"text": "Haemoglobin 10.2 g/dL 12.0-15.0", "bbox": [120, 340, 400, 28], "conf": 0.97}],
    "entities": [
        {
            "kind": "lab",
            "value": {
                "test": "Haemoglobin",
                "value": 10.2,
                "unit": "g/dL",
                "ref_low": 12.0,
                "ref_high": 15.0,
                "flag": "low",
                "date": "2026-08-12",
            },
            "text_en": "Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW",
            "bbox": [120, 340, 400, 28],
            "conf": 0.97,
            "readable": True,
        },
        {
            "kind": "drug",
            "value": {
                "name": "Metformin",
                "name_as_written": "Tab Metformin 500",
                "dose": "500 mg",
                "frequency": "twice daily",
                "duration": "30 days",
                "matched": True,
            },
            "text_en": "Metformin 500 mg twice daily",
            "bbox": [100, 500, 380, 30],
            "conf": 0.91,
            "readable": True,
        },
        {
            "kind": "drug",
            "value": {"name": None, "name_as_written": "T@b ???"},
            "text_en": "T@b ???",
            "bbox": [100, 560, 200, 30],
            "conf": 0.3,
            "readable": False,
        },
    ],
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "nlp_url", NLP)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


def session(client: TestClient, scan: bool = True) -> str:
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(
        f"/api/sessions/{sid}/consent",
        headers=K,
        json={"capture": True, "scan": scan, "share_hospital": True, "link_abha": False, "check_passed": True},
    )
    client.post(f"/api/sessions/{sid}/triage", json={"complaint_code": "fever", "redflags": NO_FLAGS}, headers=K)
    return sid


def upload(client: TestClient, sid: str, data: bytes = PNG, name: str = "p.png", ctype: str = "image/png"):
    return client.post(
        f"/api/sessions/{sid}/documents", headers=K, data={"page_no": "1"}, files={"image": (name, data, ctype)}
    )


@respx.mock
def test_upload_process_and_facts(client: TestClient, db: Session, tmp_path) -> None:
    sid = session(client)
    route = respx.post(f"{NLP}/document").mock(return_value=httpx.Response(200, json=OCR))
    doc = upload(client, sid).json()
    assert doc["status"] == "pending" or doc["status"] == "processed"  # background runs right after response
    assert route.called
    stored = db.get(Document, doc["id"])
    db.refresh(stored)
    assert (stored.status, stored.doc_type, str(stored.doc_date), stored.pinned) == (
        "processed",
        "lab_report",
        "2026-08-12",
        True,
    )
    assert stored.ocr_json["lines"][0]["bbox"] == [120, 340, 400, 28]
    assert (tmp_path / "patients" / stored.patient_id / "docs" / f"{doc['id']}.bin").read_bytes() == PNG

    facts = {f.text_en: f for f in db.exec(select(Fact).where(Fact.source_id == doc["id"]))}
    hb = facts["Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW"]
    assert (hb.section, hb.trust, hb.source_type, hb.bbox) == ("labs", "from_report", "document", [120, 340, 400, 28])
    met = facts["Metformin 500 mg twice daily"]
    assert met.section == "drugs" and met.value["found_in_documents"] is True
    bad = facts["Unreadable — see image"]
    assert bad.value["readable"] is False and bad.bbox == [100, 560, 200, 30]
    assert client.get(f"/api/documents/{doc['id']}", headers=K).json()["status"] == "processed"
    assert audit.verify_chain(db)[0]


@respx.mock
def test_nlp_failure_marks_failed(client: TestClient, db: Session) -> None:
    sid = session(client)
    respx.post(f"{NLP}/document").mock(side_effect=httpx.ConnectError("down"))
    doc = upload(client, sid, JPEG, "p.jpg", "image/jpeg").json()
    stored = db.get(Document, doc["id"])
    db.refresh(stored)
    assert stored.status == "failed"
    assert db.exec(select(Fact).where(Fact.source_id == doc["id"])).first() is None


@respx.mock
def test_discharge_summary_pinned_without_labs(client: TestClient, db: Session) -> None:
    sid = session(client)
    respx.post(f"{NLP}/document").mock(
        return_value=httpx.Response(
            200, json={"doc_type": "discharge_summary", "doc_date": None, "lines": [], "entities": []}
        )
    )
    doc = upload(client, sid).json()
    stored = db.get(Document, doc["id"])
    db.refresh(stored)
    assert stored.pinned is True and stored.doc_date is None


def test_rejections(client: TestClient) -> None:
    sid = session(client)
    assert upload(client, sid, b"GIF89a....", "x.gif", "image/gif").status_code == 422
    assert upload(client, sid, b"not an image", "x.png", "image/png").status_code == 422  # lies about its type
    big = PNG + b"\x00" * (10 * 1024 * 1024)
    assert upload(client, sid, big).status_code == 413
    no_scan = session(client, scan=False)
    res = upload(client, no_scan)
    assert res.status_code == 403 and res.json()["error"]["code"] == "forbidden"


@respx.mock
def test_image_needs_staff(client: TestClient, db: Session) -> None:
    sid = session(client)
    respx.post(f"{NLP}/document").mock(return_value=httpx.Response(200, json=OCR))
    doc = upload(client, sid).json()
    assert client.get(f"/api/documents/{doc['id']}/image", headers=K).status_code == 401
    doctor = Staff(id="D1", name="Dr. Mehta", role="doctor", department="general", pin_hash=hash_pin("1"))
    db.add(doctor)
    db.commit()
    res = client.get(f"/api/documents/{doc['id']}/image", headers={"Authorization": f"Bearer {create_jwt(doctor)}"})
    assert res.status_code == 200 and res.content == PNG and res.headers["content-type"] == "image/png"
