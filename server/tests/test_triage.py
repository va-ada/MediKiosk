from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import Answer, Fact

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}


def consented_session(client: TestClient, consent: bool = True) -> str:
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    if consent:
        client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    return sid


def triage(client: TestClient, sid: str, code: str = "joint_pain", **kw):
    body = {"complaint_code": code, "redflags": NO_FLAGS} | kw
    return client.post(f"/api/sessions/{sid}/triage", json=body, headers=K)


def test_tokens_sequential_and_departments(client: TestClient, db: Session) -> None:
    first = triage(client, consented_session(client), complaint_text="ghutne mein dard", body_part="knee").json()
    second = triage(client, consented_session(client), "fever").json()

    assert first["token"]["display"] == "A-001" and second["token"]["display"] == "A-002"
    assert first["token"]["arrival_seq"] == 1 and second["token"]["arrival_seq"] == 2
    assert first["session"]["department"] == "ayurveda" and first["session"]["pathway"] == "joint_pain"
    assert first["session"]["status"] == "triaged"
    assert second["session"]["department"] == "general" and second["session"]["pathway"] is None
    t = first["token"]
    assert t["lane"] == "normal" and t["status"] == "waiting" and t["complaint"] == "Joint pain"
    assert t["patient"] == {"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}
    assert t["flags"] == [] and t["wait_min"] == 0 and first["alerts"] == []

    fact = db.exec(select(Fact).where(Fact.session_id == first["session"]["id"])).one()
    assert (fact.section, fact.key, fact.trust, fact.patient_words) == (
        "complaint",
        "chief_complaint",
        "patient_said",
        "ghutne mein dard",
    )
    answer = db.exec(select(Answer).where(Answer.session_id == first["session"]["id"])).one()
    assert answer.question_id == "triage" and answer.slots["body_part"] == "knee"
    assert answer.slots["chest_pain"] is False and answer.slots["complaint_code"] == "joint_pain"
    assert audit.verify_chain(db)[0]


def test_retry_returns_same_token(client: TestClient) -> None:
    sid = consented_session(client)
    a = triage(client, sid).json()
    b = triage(client, sid, "fever").json()
    assert a["token"]["id"] == b["token"]["id"] and b["session"]["complaint_code"] == "joint_pain"


def test_triage_requires_consent_and_session(client: TestClient) -> None:
    res = triage(client, consented_session(client, consent=False))
    assert res.status_code == 409 and res.json()["error"]["code"] == "consent_required"
    assert triage(client, "nope").status_code == 404
    res = triage(client, consented_session(client), "sneezing")
    assert res.json()["error"]["code"] == "validation_error"
