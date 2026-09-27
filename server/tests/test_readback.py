from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import Fact, Readback
from app.routers.readback import human_duration

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}
ANSWERS = [
    ("jp_site", "knee"),
    ("jp_side", "both"),
    ("jp_duration", 90),
    ("jp_onset", "gradual"),
    ("jp_character", "aching"),
    ("jp_swelling", False),
    ("jp_stiffness", "over_30"),
    ("jp_worse", ["stairs", "cold"]),
    ("jp_better", ["heat"]),
    ("jp_severity", 6),
    ("jp_fever", False),
    ("jp_injury", False),
    ("jp_other_joints", ["none"]),
    ("jp_medicines", "Metformin 500"),
    ("jp_allergy", True),
    ("jp_allergy_detail", "Penicillin"),
]


def history(client: TestClient) -> str:
    """Real content: joint-pain pathway answered by tap."""
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    client.post(f"/api/sessions/{sid}/triage", json={"complaint_code": "joint_pain", "redflags": NO_FLAGS}, headers=K)
    for qid, v in ANSWERS:
        res = client.post(
            f"/api/sessions/{sid}/answers", json={"question_id": qid, "source": "tap", "value": v}, headers=K
        )
        assert res.status_code == 200, res.text
    return sid


def test_human_duration() -> None:
    assert human_duration(1, "en") == "1 day" and human_duration(10, "en") == "10 days"
    assert human_duration(21, "en") == "3 weeks" and human_duration(90, "hi") == "3 महीने"
    assert human_duration(30, "hi") == "4 हफ़्ते" and human_duration(730, "en") == "2 years"


def test_readback_items_hindi(client: TestClient) -> None:
    sid = history(client)
    items = client.get(f"/api/sessions/{sid}/readback?language=hi", headers=K).json()["items"]
    texts = [i["text"] for i in items]
    assert texts[0] == "मुख्य तकलीफ़: जोड़ों का दर्द"
    assert "घुटना में दर्द" in texts and "3 महीने से तकलीफ़" in texts
    assert "दर्द बढ़ता है: सीढ़ियाँ चढ़ने पर, ठंड में" in texts and "जोड़ में सूजन: नहीं" in texts
    en = {i["text_en"] for i in items}
    assert "Problem for 3 months" in en and "Pain level 6 out of 10" in en
    joined = " ".join(texts + list(en))
    for never in ("Metformin", "Penicillin", "एलर्जी", "बुखार"):  # drugs, allergies, ros are never read back
        assert never not in joined
    assert client.get(f"/api/sessions/{sid}", headers=K).json()["status"] == "verifying"


def test_responses_set_flags_and_shrink_list(client: TestClient, db: Session) -> None:
    sid = history(client)
    items = client.get(f"/api/sessions/{sid}/readback?language=en", headers=K).json()["items"]
    by_text = {i["text_en"]: i["fact_id"] for i in items}
    no_id, unsure_id, yes_id = (
        by_text["Pain in the Knee"],
        by_text["Pain level 6 out of 10"],
        by_text["Pain on the Both sides"],
    )
    for fid, r in ((no_id, "no"), (unsure_id, "not_sure"), (yes_id, "yes")):
        assert client.post(f"/api/sessions/{sid}/readback", json={"fact_id": fid, "response": r}, headers=K).json() == {
            "ok": True
        }
    db.expire_all()
    assert db.get(Fact, no_id).value == {"value": "knee", "patient_disputed": True}
    assert db.get(Fact, unsure_id).value == {"value": 6, "patient_unsure": True}
    assert db.get(Fact, yes_id).value == {"value": "both"}
    remaining = client.get(f"/api/sessions/{sid}/readback", headers=K).json()["items"]
    assert len(remaining) == len(items) - 3
    # changing a "no" to "yes" clears the dispute flag
    client.post(f"/api/sessions/{sid}/readback", json={"fact_id": no_id, "response": "yes"}, headers=K)
    db.expire_all()
    assert db.get(Fact, no_id).value == {"value": "knee"}
    assert len(db.exec(select(Readback)).all()) == 4 and audit.verify_chain(db)[0]


def test_readback_errors(client: TestClient, db: Session) -> None:
    sid = history(client)
    drug = db.exec(select(Fact).where(Fact.session_id == sid, Fact.section == "drugs")).first()
    res = client.post(f"/api/sessions/{sid}/readback", json={"fact_id": drug.id, "response": "yes"}, headers=K)
    assert res.status_code == 422
    res = client.post(f"/api/sessions/{sid}/readback", json={"fact_id": "nope", "response": "yes"}, headers=K)
    assert res.status_code == 404
    res = client.post(f"/api/sessions/{sid}/readback", json={"fact_id": drug.id, "response": "maybe"}, headers=K)
    assert res.json()["error"]["code"] == "validation_error"
