import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from fhir.resources.R4B.bundle import Bundle
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.models import Document, Fact, Outbox, Staff
from app.models import Session as Visit
from app.services import fhir

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}
NLP = "http://nlp.test"
ANSWERS = [
    ("jp_site", "knee"),
    ("jp_side", "left"),
    ("jp_duration", 90),
    ("jp_swelling", True),
    ("jp_swelling_where", ["knee", "ankle"]),
    ("jp_severity", 6),
    ("jp_medicines", "Paracetamol 650"),
    ("jp_allergy", True),
    ("jp_allergy_detail", "Penicillin — rash"),
]


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nlp_url", NLP)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")
    with respx.mock:
        respx.post(f"{NLP}/summarize").mock(return_value=httpx.Response(503))
        yield


@pytest.fixture
def h(db: Session) -> dict[str, str]:
    d = Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", room="Room 1", pin_hash=hash_pin("1"))
    db.add(d)
    db.commit()
    return {"Authorization": f"Bearer {create_jwt(d)}"}


def visit(client: TestClient, db: Session, h) -> tuple[str, str]:
    r = client.post("/api/patients/abha/verify", json={"abha_number": "12345678901234", "otp": "123456"}, headers=K)
    pid = r.json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    tok = client.post(
        f"/api/sessions/{sid}/triage",
        headers=K,
        json={"complaint_code": "joint_pain", "complaint_text": "ghutne mein dard", "redflags": NO_FLAGS},
    ).json()["token"]
    for qid, v in ANSWERS:
        client.post(f"/api/sessions/{sid}/answers", json={"question_id": qid, "source": "tap", "value": v}, headers=K)
    doc = Document(session_id=sid, patient_id=pid, file_path="x", doc_type="lab_report", status="processed")
    db.add(doc)
    db.flush()
    db.add(
        Fact(
            session_id=sid,
            patient_id=pid,
            section="labs",
            key="Haemoglobin",
            trust="from_report",
            source_type="document",
            source_id=doc.id,
            text_en="Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW",
            value={
                "test": "Haemoglobin",
                "value": 10.2,
                "unit": "g/dL",
                "ref_low": 12.0,
                "ref_high": 15.0,
                "flag": "low",
                "date": "2026-08-12",
            },
        )
    )
    db.commit()
    client.post(f"/api/sessions/{sid}/submit", headers=K)
    client.post(f"/api/sessions/{sid}/ayush-exam", json={"pramana": {"height_cm": 158, "weight_kg": 64}}, headers=h)
    client.post(
        f"/api/sessions/{sid}/diagnosis",
        headers=h,
        json={
            "codes": [{"system": "NAMASTE", "code": "SAMPLE-NAM-001", "display": "Sandhigata Vata"}],
            "text": "Early OA",
        },
    )
    return sid, tok["id"]


def kinds(bundle: dict) -> list[str]:
    return [e["resource"]["resourceType"] for e in bundle["entry"]]


def test_bundle_is_valid_r4b_with_trust_tags(client: TestClient, db: Session, h) -> None:
    sid, _ = visit(client, db, h)
    side = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "side")).one()
    side.trust = "rejected"
    db.add(side)
    db.commit()
    bundle = fhir.build_bundle(db, db.get(Visit, sid))
    parsed = Bundle.model_validate(bundle)  # parses back with fhir.resources R4B
    assert parsed.type == "collection"
    k = kinds(bundle)
    for needed in (
        "Patient",
        "Encounter",
        "Condition",
        "AllergyIntolerance",
        "MedicationStatement",
        "Observation",
        "QuestionnaireResponse",
        "Composition",
    ):
        assert needed in k, needed
    assert k.count("Condition") == 2  # chief complaint + coded diagnosis
    for e in bundle["entry"]:
        tag = e["resource"]["meta"]["tag"][0]
        assert tag["system"] == "urn:medikiosk:trust" and tag["code"] in {
            "patient_said",
            "from_report",
            "doctor_verified",
        }
    by = {r["resourceType"]: r for r in (e["resource"] for e in bundle["entry"])}
    assert {"system": "urn:medikiosk:abha-number", "value": "12345678901234"} in by["Patient"]["identifier"]
    lab = next(
        e["resource"]
        for e in bundle["entry"]
        if e["resource"]["resourceType"] == "Observation" and e["resource"]["category"][0]["text"] == "laboratory"
    )
    assert lab["valueQuantity"] == {"value": 10.2, "unit": "g/dL"}
    assert lab["referenceRange"][0]["low"]["value"] == 12.0 and lab["interpretation"][0]["coding"][0]["code"] == "L"
    assert by["AllergyIntolerance"]["code"]["text"] == "Penicillin — rash"
    qr_items = {i["linkId"]: i for i in by["QuestionnaireResponse"]["item"]}
    assert [a["valueString"] for a in qr_items["jp_swelling_where"]["answer"]] == ["knee", "ankle"]
    assert qr_items["triage.chest_pain"]["answer"] == [{"valueBoolean": False}]
    assert "Side: Left" not in str(bundle)  # rejected facts never leave the hospital
    assert "Pramana: height 158 cm, weight 64 kg, BMI 25.6" in str(bundle)


def test_outcome_out_enqueues_once(client: TestClient, db: Session, h) -> None:
    sid, tid = visit(client, db, h)
    client.post(f"/api/tokens/{tid}/in", headers=h)
    assert client.post(f"/api/tokens/{tid}/outcome", json={"outcome": "out"}, headers=h).status_code == 200
    rows = db.exec(select(Outbox).where(Outbox.session_id == sid)).all()
    assert len(rows) == 1
    ob = rows[0]
    assert ob.status == "pending" and ob.kind == "fhir_bundle" and ob.idempotency_key.startswith(f"{sid}:v")
    Bundle.model_validate(ob.payload)
    enc = next(e["resource"] for e in ob.payload["entry"] if e["resource"]["resourceType"] == "Encounter")
    assert enc["status"] == "finished" and "end" in enc["period"]
    assert fhir.enqueue_bundle(db, db.get(Visit, sid)).id == ob.id  # same summary version → same row
    assert audit.verify_chain(db)[0]
