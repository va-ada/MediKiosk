import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.auth import create_jwt, hash_pin
from app.config import settings
from app.ids import utcnow
from app.models import Alert, Document, Fact, Staff, Summary
from app.models import Session as Visit

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}
NLP = "http://nlp.test"
ANSWERS = [
    ("jp_site", "knee"),
    ("jp_side", "left"),
    ("jp_duration", 90),
    ("jp_onset", "gradual"),
    ("jp_character", "aching"),
    ("jp_swelling", False),
    ("jp_stiffness", "none"),
    ("jp_worse", ["stairs"]),
    ("jp_better", ["rest"]),
    ("jp_severity", 6),
    ("jp_fever", False),
    ("jp_injury", False),
    ("jp_other_joints", ["none"]),
    ("jp_medicines", "Paracetamol 650"),
    ("jp_allergy", True),
    ("jp_allergy_detail", "Penicillin — rash"),
]
TOP_KEYS = {
    "session_id",
    "version",
    "generated_at",
    "patient",
    "informant",
    "token",
    "critical",
    "sections",
    "documents",
    "new_since_opened",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "nlp_url", NLP)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


@pytest.fixture
def doc_h(db: Session) -> dict[str, str]:
    d = Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", room="Room 1", pin_hash=hash_pin("1"))
    db.add(d)
    db.commit()
    return {"Authorization": f"Bearer {create_jwt(d)}"}


def intake(client: TestClient, pid: str | None = None, answers=ANSWERS) -> tuple[str, str]:
    if pid is None:
        pid = client.post(
            "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
        ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    client.post(
        f"/api/sessions/{sid}/triage",
        headers=K,
        json={
            "complaint_code": "joint_pain",
            "complaint_text": "ghutne mein dard",
            "redflags": NO_FLAGS | {"fainted": True},
        },
    )
    for qid, v in answers:
        client.post(f"/api/sessions/{sid}/answers", json={"question_id": qid, "source": "tap", "value": v}, headers=K)
    return pid, sid


def add_report_facts(db: Session, sid: str, pid: str) -> None:
    doc = Document(
        session_id=sid, patient_id=pid, file_path="docs/x.bin", doc_type="lab_report", status="processed", pinned=True
    )
    db.add(doc)
    db.flush()
    db.add_all(
        [
            Fact(
                session_id=sid,
                patient_id=pid,
                section="labs",
                key="Haemoglobin",
                trust="from_report",
                source_type="document",
                source_id=doc.id,
                bbox=[1, 2, 3, 4],
                text_en="Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW",
                value={
                    "test": "Haemoglobin",
                    "value": 10.2,
                    "unit": "g/dL",
                    "ref_low": 12,
                    "ref_high": 15,
                    "flag": "low",
                },
            ),
            Fact(
                session_id=sid,
                patient_id=pid,
                section="drugs",
                key="Metformin",
                trust="from_report",
                source_type="document",
                source_id=doc.id,
                text_en="Metformin 500 mg twice daily",
                value={"name": "Metformin", "found_in_documents": True},
            ),
            Fact(
                session_id=sid,
                patient_id=pid,
                section="drugs",
                key="x",
                trust="from_report",
                source_type="document",
                source_id=doc.id,
                text_en="Unreadable — see image",
                value={"readable": False},
            ),
        ]
    )
    db.commit()


@respx.mock
def test_submit_and_summary_shape(client: TestClient, db: Session, doc_h) -> None:
    summ = respx.post(f"{NLP}/summarize").mock(
        return_value=httpx.Response(
            200,
            json={
                "narrative": "Left knee pain for 3 months, worse on stairs.",
                "unsupported_terms": [],
                "fallback_used": False,
            },
        )
    )
    pid, sid = intake(client)
    add_report_facts(db, sid, pid)
    res = client.post(f"/api/sessions/{sid}/submit", headers=K).json()
    assert res["session"]["status"] == "submitted" and res["summary_version"] == 1

    s = client.get(f"/api/sessions/{sid}/summary", headers=doc_h).json()
    assert (
        set(s) == TOP_KEYS and s["version"] == 1 and s["generated_at"].endswith("Z")
    )  # nothing changed → same version
    assert s["patient"]["hospital_id"].startswith("MK-") and s["token"]["department"] == "ayurveda"
    assert s["informant"] == {"type": "self", "relation": None}
    crit = s["critical"]
    assert [a["text"] for a in crit["allergies"]] == ["Penicillin — rash"]
    assert [r["text"] for r in crit["red_flags"]] == ["Fainted today"]
    assert crit["abnormal_labs"][0]["text"].startswith("Haemoglobin 10.2")
    keys = [sec["key"] for sec in s["sections"]]
    assert keys == ["complaint", "hpi", "allergies", "drugs", "labs", "ros"]  # §2 display order, empty ones omitted
    hpi = s["sections"][1]
    assert hpi["narrative"] == "Left knee pain for 3 months, worse on stairs." and hpi["narrative_ai"] is True
    duration = next(i for i in hpi["items"] if i["text"] == "Duration: 90 days")
    assert set(duration) == {"fact_id", "text", "trust", "patient_words", "flags"} and duration["flags"] == []
    drugs = s["sections"][3]["items"]
    assert [(d["text"], d["found_in_documents"]) for d in drugs] == [
        ("Medicine (patient reported): Paracetamol 650", False),
        ("Metformin 500 mg twice daily", True),
        ("Unreadable — see image", True),
    ]
    assert set(drugs[1]["source"]) == {"document_id", "bbox"}
    assert drugs[2]["flags"] == ["unreadable"]
    assert s["documents"][0]["pinned"] is True and s["documents"][0]["image_url"].startswith("/api/documents/")
    assert s["sections"][0]["items"][0]["patient_words"] == "ghutne mein dard"
    visit = db.get(Visit, sid)
    db.refresh(visit)
    assert visit.status == "with_doctor" and visit.opened_by_doctor_at is not None
    assert summ.call_count == 1  # narrative reused while HPI facts are unchanged
    assert audit.verify_chain(db)[0]


@respx.mock
def test_fallback_rejected_new_since_and_versions(client: TestClient, db: Session, doc_h) -> None:
    respx.post(f"{NLP}/summarize").mock(side_effect=httpx.ConnectError("down"))
    pid, sid = intake(client, answers=ANSWERS[:3])
    client.post(f"/api/sessions/{sid}/submit", headers=K)
    s = client.get(f"/api/sessions/{sid}/summary", headers=doc_h).json()
    hpi = next(x for x in s["sections"] if x["key"] == "hpi")
    assert hpi["narrative_ai"] is False and "Duration: 90 days" in hpi["narrative"] and "; " in hpi["narrative"]
    v1 = s["version"]

    site = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "site")).one()
    site.trust = "rejected"
    db.add(site)
    db.add(
        Fact(
            session_id=sid,
            patient_id=pid,
            section="pmh",
            key="dm",
            text_en="Diabetes for 5 years",
            trust="patient_said",
            source_type="answer",
            value={"value": True},
            created_at=utcnow(),
        )
    )
    db.commit()
    s2 = client.get(f"/api/sessions/{sid}/summary", headers=doc_h).json()
    assert s2["version"] == v1 + 1
    texts = [i["text"] for sec in s2["sections"] for i in sec["items"]]
    assert "Site: Knee" not in texts and "Diabetes for 5 years" in texts
    assert [n["text"] for n in s2["new_since_opened"]] == ["Diabetes for 5 years"]
    assert len(db.exec(select(Summary).where(Summary.session_id == sid)).all()) == 2


def test_allergy_always_shown_and_no_allergy_text(client: TestClient, db: Session, doc_h) -> None:
    with respx.mock:
        respx.post(f"{NLP}/summarize").mock(return_value=httpx.Response(503))
        _, sid = intake(client, answers=ANSWERS[:14] + [("jp_allergy", False)])
        s = client.get(f"/api/sessions/{sid}/summary", headers=doc_h).json()
        assert [a["text"] for a in s["critical"]["allergies"]] == ["No known allergies (patient said)"]
        _, sid2 = intake(client)
        detail = db.exec(select(Fact).where(Fact.session_id == sid2, Fact.key == "allergy_detail")).one()
        detail.trust = "rejected"
        db.add(detail)
        db.commit()
        s = client.get(f"/api/sessions/{sid2}/summary", headers=doc_h).json()
        assert [(a["text"], a["trust"]) for a in s["critical"]["allergies"]] == [("Penicillin — rash", "rejected")]


def test_carried_facts_copied_once(client: TestClient, db: Session, doc_h) -> None:
    with respx.mock:
        respx.post(f"{NLP}/summarize").mock(return_value=httpx.Response(503))
        pid, sid = intake(client)
        for f in db.exec(select(Fact).where(Fact.session_id == sid, Fact.section.in_(["allergies", "drugs"]))):
            f.trust = "doctor_verified"
            db.add(f)
        db.commit()
        _, sid2 = intake(client, pid=pid, answers=ANSWERS[:2])
        s = client.get(f"/api/sessions/{sid2}/summary", headers=doc_h).json()
        client.get(f"/api/sessions/{sid2}/summary", headers=doc_h)
        carried = db.exec(select(Fact).where(Fact.session_id == sid2, Fact.source_type == "carried")).all()
        assert len(carried) == 3  # allergy yes + detail + one medicine, copied once
        assert all(c.trust == "doctor_verified" for c in carried)
        drug = next(i for sec in s["sections"] if sec["key"] == "drugs" for i in sec["items"])
        assert "carried" in drug["flags"] and drug["trust"] == "doctor_verified"


def test_submit_rules_and_auth(client: TestClient, db: Session, doc_h) -> None:
    pid = client.post(
        "/api/patients/register", json={"name": "A", "age": 3, "sex": "M", "language": "en"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    assert client.post(f"/api/sessions/{sid}/submit", headers=K).json()["error"]["code"] == "invalid_state"
    assert client.get(f"/api/sessions/{sid}/summary", headers=K).status_code == 401
    assert db.exec(select(Alert)).all() == []
