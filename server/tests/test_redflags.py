import pytest
import yaml
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.models import Alert
from app.services import graph, redflags
from app.ws import hub

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}

INLINE = yaml.safe_load("""
rules:
  - id: both
    level: emergency
    reason_text: "A and B"
    all: [{slot: a, is: true}, {slot: b, is: true}]
  - id: any_c
    level: urgent
    reason_text: "C or D"
    any: [{slot: c, is: true}, {slot: d, gte: 9}]
  - id: all_and_any
    level: urgent
    reason_text: "E plus one of F/G"
    all: [{slot: e, is: true}]
    any: [{slot: f, in: [x, y]}, {slot: g, lte: 2}]
  - id: a_not_b
    level: urgent
    reason_text: "A without B"
    all: [{slot: a, is: true}, {slot: b, is: false}]
""")["rules"]


@pytest.fixture
def inline_rules():
    redflags.set_rules(INLINE)
    yield
    redflags.set_rules(None)


def ids(slots: dict) -> list[str]:
    return [r["id"] for r in redflags.evaluate(slots)]


def test_all_any_semantics(inline_rules) -> None:
    assert ids({"a": True, "b": True}) == ["both"]
    assert ids({"a": True, "b": False}) == ["a_not_b"]
    assert ids({"a": True}) == []  # unanswered b: neither rule
    assert ids({"c": True}) == ["any_c"] and ids({"d": 9}) == ["any_c"] and ids({"d": 8}) == []
    assert ids({"e": True, "f": "y"}) == ["all_and_any"]
    assert ids({"e": True, "f": ["q", "x"]}) == ["all_and_any"]
    assert ids({"e": True, "g": 2}) == ["all_and_any"] and ids({"e": True, "g": 3}) == []
    assert ids({"e": False, "f": "x"}) == []
    assert ids({"d": "nine"}) == []  # wrong type never fires


def test_real_rules_file_loads() -> None:
    fired = ids(
        {"chest_pain": True, "breathless": True, "fainted": True, "stroke_signs": False, "heavy_bleeding": False}
    )
    assert fired == ["chest_pain_breathless", "fainted_today"]
    assert ids({"chest_pain": True, "breathless": False}) == ["chest_pain_only"]
    assert ids({"severity": 9}) == ["severe_pain"] and ids({"fever": True, "swelling": True}) == ["fever_with_swelling"]


def _triage(client: TestClient, flags: dict) -> dict:
    pid = client.post(
        "/api/patients/register", json={"name": "Ram", "age": 70, "sex": "M", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    return client.post(
        f"/api/sessions/{sid}/triage", json={"complaint_code": "chest_pain", "redflags": flags}, headers=K
    ).json()


def test_triage_chest_pain_breathless_creates_emergency(client: TestClient, db: Session, monkeypatch) -> None:
    sent: list[tuple] = []
    monkeypatch.setattr(hub, "emit", lambda ch, t, d: sent.append((tuple(ch) if not isinstance(ch, str) else ch, t, d)))
    res = _triage(client, NO_FLAGS | {"chest_pain": True, "breathless": True})
    assert [a["rule_id"] for a in res["alerts"]] == ["chest_pain_breathless"]
    a = res["alerts"][0]
    assert (a["level"], a["source"], a["status"], a["kiosk_id"]) == ("emergency", "rule", "open", "KIOSK-01")
    assert "red_flag" in res["token"]["flags"]
    alert_events = [s for s in sent if s[1] == "alert.created"]
    assert alert_events == [(("alerts", "admin"), "alert.created", alert_events[0][2])]
    assert alert_events[0][2]["id"] == a["id"]
    assert audit.verify_chain(db)[0]


def test_no_flags_no_alert(client: TestClient, db: Session) -> None:
    assert _triage(client, NO_FLAGS)["alerts"] == []
    assert db.exec(select(Alert)).all() == []


def test_alert_once_per_session_rule(client: TestClient, db: Session) -> None:
    tiny = [
        {
            "id": "joint_pain",
            "start": "q",
            "questions": [
                {
                    "id": "q",
                    "type": "scale",
                    "section": "hpi",
                    "text_en": "Pain?",
                    "text_hi": "दर्द?",
                    "slot": {"name": "severity", "type": "scale_0_10"},
                    "next": "q2",
                },
                {
                    "id": "q2",
                    "type": "yesno",
                    "section": "hpi",
                    "text_en": "More?",
                    "text_hi": "और?",
                    "slot": {"name": "more", "type": "bool"},
                    "next": "end",
                },
            ],
        }
    ]
    graph.set_graph(graph.Graph.from_docs(tiny))
    try:
        pid = client.post(
            "/api/patients/register", json={"name": "S", "age": 50, "sex": "F", "language": "hi"}, headers=K
        ).json()["id"]
        sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
        client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
        client.post(
            f"/api/sessions/{sid}/triage", json={"complaint_code": "joint_pain", "redflags": NO_FLAGS}, headers=K
        )
        r = client.post(
            f"/api/sessions/{sid}/answers", json={"question_id": "q", "source": "tap", "value": 10}, headers=K
        ).json()
        assert [a["rule_id"] for a in r["alerts"]] == ["severe_pain"]
        r = client.post(
            f"/api/sessions/{sid}/answers", json={"question_id": "q2", "source": "tap", "value": True}, headers=K
        ).json()
        assert r["alerts"] == []
        assert len(db.exec(select(Alert).where(Alert.session_id == sid)).all()) == 1
    finally:
        graph.set_graph(None)
