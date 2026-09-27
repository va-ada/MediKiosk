import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import Fact
from app.models import Session as Visit
from app.services import graph

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}

TINY = [
    {
        "id": "joint_pain",
        "start": "q_site",
        "questions": [
            {
                "id": "q_site",
                "type": "choice",
                "section": "complaint",
                "text_en": "Which joint?",
                "text_hi": "कौन सा जोड़?",
                "slot": {"name": "site", "type": "enum"},
                "choices": [
                    {"value": "knee", "en": "Knee", "hi": "घुटना", "icon": "knee"},
                    {"value": "back", "en": "Lower back", "hi": "कमर", "icon": "back"},
                ],
                "next": "q_swelling",
            },
            {
                "id": "q_swelling",
                "type": "yesno",
                "section": "hpi",
                "text_en": "Is it swollen?",
                "text_hi": "सूजन?",
                "slot": {"name": "swelling", "type": "bool"},
                "next": [{"if": {"slot": "swelling", "is": True}, "goto": "q_where"}, {"goto": "q_days"}],
            },
            {
                "id": "q_where",
                "type": "multi",
                "section": "hpi",
                "text_en": "Where?",
                "text_hi": "कहाँ?",
                "slot": {"name": "where", "type": "list_enum"},
                "choices": [
                    {"value": "knee", "en": "Knee", "hi": "घुटना"},
                    {"value": "ankle", "en": "Ankle", "hi": "टखना"},
                ],
                "next": "q_days",
            },
            {
                "id": "q_days",
                "type": "duration",
                "section": "hpi",
                "text_en": "How long?",
                "text_hi": "कब से?",
                "slot": {"name": "duration_days", "type": "duration_days"},
                "next": [{"if": {"slot": "fainted", "is": True}, "goto": "q_meds"}, {"goto": "q_pain"}],
            },
            {
                "id": "q_pain",
                "type": "scale",
                "section": "hpi",
                "text_en": "How bad?",
                "text_hi": "कितना?",
                "slot": {"name": "severity", "type": "scale_0_10"},
                "next": "q_meds",
            },
            {
                "id": "q_meds",
                "type": "free",
                "section": "drugs",
                "text_en": "Medicines?",
                "text_hi": "दवाइयाँ?",
                "slot": {"name": "current_medicines", "type": "list_string"},
                "choices": [
                    {"value": "none", "en": "None", "hi": "कोई नहीं"},
                    {"value": "not_sure", "en": "Not sure", "hi": "पता नहीं"},
                ],
                "next": "end",
            },
        ],
    },
    {
        "id": "ayush",
        "start": "a_sleep",
        "questions": [
            {
                "id": "a_sleep",
                "type": "number",
                "section": "ayush",
                "text_en": "Hours of sleep?",
                "text_hi": "नींद?",
                "doctor_note": "Nidra",
                "slot": {"name": "sleep_hours", "type": "number"},
                "next": "end",
            },
        ],
    },
]


@pytest.fixture(autouse=True)
def tiny_graph():
    graph.set_graph(graph.Graph.from_docs(TINY))
    yield
    graph.set_graph(None)


def start(client: TestClient, redflags: dict | None = None, code: str = "joint_pain") -> str:
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    client.post(
        f"/api/sessions/{sid}/triage", json={"complaint_code": code, "redflags": redflags or NO_FLAGS}, headers=K
    )
    return sid


def nxt(client: TestClient, sid: str, lang: str = "hi") -> dict:
    return client.get(f"/api/sessions/{sid}/next-question?language={lang}", headers=K).json()


def answer(client: TestClient, sid: str, qid: str, value) -> dict:
    return client.post(
        f"/api/sessions/{sid}/answers", json={"question_id": qid, "source": "tap", "value": value}, headers=K
    )


def test_render_shape_and_language(client: TestClient) -> None:
    sid = start(client)
    q = nxt(client, sid)["question"]
    assert set(q) == {"id", "type", "section", "text", "text_en", "audio", "choices", "slot", "allow_voice", "progress"}
    assert q["id"] == "q_site" and q["text"] == "कौन सा जोड़?" and q["audio"] == "q_site"
    assert q["choices"][0] == {"value": "knee", "label": "घुटना", "en": "Knee", "hi": "घुटना", "icon": "knee"}
    assert q["progress"] == {"answered": 0, "remaining_estimate": 5 + 1}  # default path + ayush
    assert nxt(client, sid, "en")["question"]["text"] == "Which joint?"


def test_full_walk_with_branch(client: TestClient, db: Session) -> None:
    sid = start(client)
    r = answer(client, sid, "q_site", "knee").json()
    assert r["next"]["question"]["id"] == "q_swelling" and r["alerts"] == []
    assert r["answer"]["slots"] == {"site": "knee"}
    assert answer(client, sid, "q_swelling", True).json()["next"]["question"]["id"] == "q_where"
    r = answer(client, sid, "q_where", ["ankle", "knee", "ankle"]).json()
    assert r["answer"]["slots"] == {"where": ["ankle", "knee"]}
    assert answer(client, sid, "q_days", 90).json()["next"]["question"]["id"] == "q_pain"
    answer(client, sid, "q_pain", 7)
    r = answer(client, sid, "q_meds", "Metformin 500, amlodipine").json()
    q = r["next"]["question"]
    assert q["id"] == "a_sleep" and "doctor_note" not in q and "Nidra" not in str(q)  # ayurveda → ayush
    r = answer(client, sid, "a_sleep", 6).json()
    assert r["next"] == {"done": True}
    assert db.get(Visit, sid).status == "documents"

    facts = {f.key: f for f in db.exec(select(Fact).where(Fact.session_id == sid))}
    assert facts["site"].text_en == "Site: Knee" and facts["site"].value == {"value": "knee"}
    assert facts["swelling"].text_en == "Yes: Is it swollen?" and facts["swelling"].trust == "patient_said"
    assert facts["duration_days"].text_en == "Duration: 90 days"
    assert facts["severity"].text_en == "Severity: 7/10"
    meds = db.exec(select(Fact).where(Fact.session_id == sid, Fact.section == "drugs")).all()
    assert sorted(m.value["name"] for m in meds) == ["Metformin 500", "amlodipine"]
    assert all(m.value["found_in_documents"] is False for m in meds)
    assert audit.verify_chain(db)[0]


def test_no_branch_and_triage_slot_condition(client: TestClient) -> None:
    sid = start(client, redflags=NO_FLAGS | {"fainted": True})
    answer(client, sid, "q_site", "back")
    assert answer(client, sid, "q_swelling", "no").json()["next"]["question"]["id"] == "q_days"
    # triage slot `fainted` drives the rule: skip q_pain
    assert answer(client, sid, "q_days", 3).json()["next"]["question"]["id"] == "q_meds"


def test_reanswer_replaces_fact(client: TestClient, db: Session) -> None:
    sid = start(client)
    answer(client, sid, "q_site", "knee")
    answer(client, sid, "q_site", "back")
    facts = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "site")).all()
    assert [f.value["value"] for f in facts] == ["back"]


def test_tap_fallbacks_for_free_questions(client: TestClient, db: Session) -> None:
    sid = start(client)
    for qid, v in (("q_site", "knee"), ("q_swelling", False), ("q_days", 10), ("q_pain", 3)):
        answer(client, sid, qid, v)
    assert answer(client, sid, "q_meds", "none").json()["answer"]["slots"] == {"current_medicines": []}
    f = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "current_medicines")).one()
    assert f.text_en == "Current medicines: none"
    answer(client, sid, "q_meds", "not_sure")
    f = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "current_medicines")).one()
    assert f.value == {"value": None, "patient_unsure": True}


def test_validation_and_states(client: TestClient) -> None:
    sid = start(client)
    for qid, bad in (
        ("q_site", "elbow"),
        ("q_swelling", "maybe"),
        ("q_pain", 11),
        ("q_days", "x"),
        ("q_where", ["knee", "hip"]),
    ):
        res = answer(client, sid, qid, bad)
        assert res.status_code == 422 and res.json()["error"]["code"] == "validation_error", (qid, bad)
    assert answer(client, sid, "nope", 1).status_code == 404
    # general complaint with no pathway → done straight away
    assert nxt(client, start(client, code="fever")) == {"done": True}
    # not triaged yet → invalid_state
    pid = client.post(
        "/api/patients/register", json={"name": "A", "age": 1, "sex": "M", "language": "en"}, headers=K
    ).json()["id"]
    raw = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    assert client.get(f"/api/sessions/{raw}/next-question", headers=K).json()["error"]["code"] == "invalid_state"


def test_condition_ops() -> None:
    slots = {"n": 5, "l": ["a", "b"], "s": "x", "none": None}
    assert graph.condition_holds({"slot": "n", "gte": 5}, slots)
    assert not graph.condition_holds({"slot": "n", "lte": 4}, slots)
    assert graph.condition_holds({"slot": "l", "in": ["b", "z"]}, slots)
    assert graph.condition_holds({"slot": "s", "in": ["x"]}, slots)
    assert not graph.condition_holds({"slot": "missing", "is": True}, slots)
    assert not graph.condition_holds({"slot": "none", "gte": 1}, slots)
    assert not graph.condition_holds({"slot": "s", "gte": 1}, slots)  # type mismatch is just false
