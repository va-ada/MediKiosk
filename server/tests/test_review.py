import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.models import Diagnosis, Fact, Staff

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}
NLP = "http://nlp.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "nlp_url", NLP)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")
    with respx.mock:
        respx.post(f"{NLP}/summarize").mock(return_value=httpx.Response(503))
        yield


@pytest.fixture
def h(db: Session) -> dict[str, dict[str, str]]:
    rows = [
        Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", pin_hash=hash_pin("1")),
        Staff(id="D2", name="Dr. Rao", role="doctor", department="general", pin_hash=hash_pin("1")),
        Staff(id="N1", name="Nurse", role="nurse", pin_hash=hash_pin("1")),
    ]
    db.add_all(rows)
    db.commit()
    return {s.id: {"Authorization": f"Bearer {create_jwt(s)}"} for s in rows}


def submitted(client: TestClient) -> str:
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    client.post(f"/api/sessions/{sid}/triage", json={"complaint_code": "joint_pain", "redflags": NO_FLAGS}, headers=K)
    for qid, v in (("jp_site", "knee"), ("jp_side", "left"), ("jp_duration", 90)):
        client.post(f"/api/sessions/{sid}/answers", json={"question_id": qid, "source": "tap", "value": v}, headers=K)
    client.post(f"/api/sessions/{sid}/submit", headers=K)
    return sid


def summary(client: TestClient, sid: str, hdr: dict) -> dict:
    return client.get(f"/api/sessions/{sid}/summary", headers=hdr).json()


def test_open_then_approve_section(client: TestClient, db: Session, h) -> None:
    sid = submitted(client)
    v0 = summary(client, sid, h["D1"])["version"]
    res = client.post(f"/api/sessions/{sid}/sections/complaint/approve", headers=h["D1"])
    assert res.status_code == 409 and res.json()["error"]["code"] == "section_not_opened"
    assert client.post(f"/api/sessions/{sid}/sections/complaint/open", headers=h["D1"]).json() == {"ok": True}
    # another doctor can't approve a section only D1 opened
    assert client.post(f"/api/sessions/{sid}/sections/complaint/approve", headers=h["D2"]).status_code == 409
    assert client.post(f"/api/sessions/{sid}/sections/complaint/approve", headers=h["D1"]).json() == {"ok": True}
    s = summary(client, sid, h["D1"])
    complaint = s["sections"][0]
    assert complaint["opened"] and complaint["approved"] and s["version"] > v0
    assert {i["trust"] for i in complaint["items"]} == {"doctor_verified"}
    hpi = next(x for x in s["sections"] if x["key"] == "hpi")
    assert {i["trust"] for i in hpi["items"]} == {"patient_said"}  # other sections untouched
    assert client.post(f"/api/sessions/{sid}/sections/bogus/open", headers=h["D1"]).status_code == 404
    assert client.post(f"/api/sessions/{sid}/sections/hpi/open", headers=h["N1"]).status_code == 403
    assert audit.verify_chain(db)[0]


def test_fact_verify_actions(client: TestClient, db: Session, h) -> None:
    sid = submitted(client)
    facts = {f.key: f for f in db.exec(select(Fact).where(Fact.session_id == sid))}
    ok = client.post(f"/api/facts/{facts['site'].id}/verify", json={"action": "approve"}, headers=h["D1"]).json()
    assert ok["trust"] == "doctor_verified" and ok["verified_by"] == "D1" and ok["verified_at"].endswith("Z")
    ed = client.post(
        f"/api/facts/{facts['duration_days'].id}/verify",
        headers=h["D1"],
        json={"action": "edit", "value": {"value": 60}, "text_en": "Duration: 60 days"},
    ).json()
    assert (ed["trust"], ed["value"], ed["text_en"]) == ("doctor_verified", {"value": 60}, "Duration: 60 days")
    rj = client.post(f"/api/facts/{facts['side'].id}/verify", json={"action": "reject"}, headers=h["D1"]).json()
    assert rj["trust"] == "rejected"
    texts = [i["text"] for sec in summary(client, sid, h["D1"])["sections"] for i in sec["items"]]
    assert "Side: Left" not in texts and "Duration: 60 days" in texts
    bad = client.post(f"/api/facts/{facts['site'].id}/verify", json={"action": "edit"}, headers=h["D1"])
    assert bad.status_code == 422
    assert client.post("/api/facts/nope/verify", json={"action": "approve"}, headers=h["D1"]).status_code == 404


def test_ayush_exam_and_bmi(client: TestClient, db: Session, h) -> None:
    sid = submitted(client)
    body = {
        "nadi": {"value": "vata", "note": "fast, irregular"},
        "jihva": "coated",
        "pramana": {"height_cm": 160, "weight_kg": 62},
        "notes": "Tenderness medial joint line",
    }
    facts = client.post(f"/api/sessions/{sid}/ayush-exam", json=body, headers=h["D1"]).json()["facts"]
    texts = {f["key"]: f["text_en"] for f in facts}
    assert texts["exam_nadi"] == "Nadi: vata — fast, irregular" and texts["exam_jihva"] == "Jihva: coated"
    assert texts["exam_pramana"] == "Pramana: height 160 cm, weight 62 kg, BMI 24.2"
    assert all(
        f["trust"] == "doctor_verified" and f["section"] == "ayush" and f["source_type"] == "doctor" for f in facts
    )
    # re-saving replaces, doesn't duplicate
    client.post(f"/api/sessions/{sid}/ayush-exam", json={"jihva": "clean"}, headers=h["D1"])
    jihva = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "exam_jihva")).all()
    assert [f.text_en for f in jihva] == ["Jihva: clean"]
    ay = next(x for x in summary(client, sid, h["D1"])["sections"] if x["key"] == "ayush")
    assert "Pramana: height 160 cm, weight 62 kg, BMI 24.2" in [i["text"] for i in ay["items"]]
    assert client.post(f"/api/sessions/{sid}/ayush-exam", json={}, headers=h["D1"]).status_code == 422
    assert (
        client.post(
            f"/api/sessions/{sid}/ayush-exam", json={"pramana": {"height_cm": 0, "weight_kg": 60}}, headers=h["D1"]
        ).status_code
        == 422
    )


def test_diagnosis(client: TestClient, db: Session, h) -> None:
    sid = submitted(client)
    codes = [{"system": "NAMASTE", "code": "SAMPLE-NAM-001", "display": "Sandhigata Vata"}]
    assert client.post(
        f"/api/sessions/{sid}/diagnosis", json={"codes": codes, "text": "Early OA knee"}, headers=h["D1"]
    ).json() == {"ok": True}
    d = db.exec(select(Diagnosis).where(Diagnosis.session_id == sid)).one()
    assert d.codes == codes and d.staff_id == "D1"
    assert client.post(f"/api/sessions/{sid}/diagnosis", json={"codes": []}, headers=h["D1"]).status_code == 422
    bad = [{"system": "SNOMED", "code": "x", "display": "y"}]
    assert client.post(f"/api/sessions/{sid}/diagnosis", json={"codes": bad}, headers=h["D1"]).status_code == 422
