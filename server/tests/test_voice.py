import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import audit
from app.config import settings
from app.models import Answer, Fact

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False, "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": False, "check_passed": True}
NLP = "http://nlp.test"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "nlp_url", NLP)
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def session(client: TestClient) -> str:
    """Real joint-pain content; first question is jp_site."""
    pid = client.post(
        "/api/patients/register", json={"name": "Kamla", "age": 62, "sex": "F", "language": "hi"}, headers=K
    ).json()["id"]
    sid = client.post("/api/sessions", json={"patient_id": pid, "informant": "self"}, headers=K).json()["id"]
    client.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K)
    client.post(f"/api/sessions/{sid}/triage", json={"complaint_code": "joint_pain", "redflags": NO_FLAGS}, headers=K)
    return sid


def speak(client: TestClient, sid: str, qid: str, filename: str = "a.m4a", ctype: str = "audio/mp4"):
    return client.post(
        f"/api/sessions/{sid}/answers/audio",
        headers=K,
        data={"question_id": qid, "language": "hi"},
        files={"audio": (filename, b"\x00fake-audio\x01", ctype)},
    )


@respx.mock
def test_confident_voice_answer(client: TestClient, db: Session, tmp_path) -> None:
    sid = session(client)
    asr = respx.post(f"{NLP}/asr").mock(
        return_value=httpx.Response(200, json={"text": "घुटने में दर्द है", "confidence": 0.85, "duration_sec": 2.1})
    )
    ext = respx.post(f"{NLP}/extract").mock(
        return_value=httpx.Response(200, json={"slots": {"site": "knee"}, "status": "confident", "notes": []})
    )
    res = speak(client, sid, "jp_site").json()
    assert res["answer"]["source"] == "voice" and res["answer"]["status"] == "confident"
    assert res["answer"]["raw_text"] == "घुटने में दर्द है" and res["answer"]["confidence"] == 0.85
    assert res["next"]["question"]["id"] == "jp_side" and res["fallback_choices"] == []
    sent = ext.calls.last.request
    body = httpx.Response(200, content=sent.content).json()
    assert body["slots"] == [
        {"name": "site", "type": "enum", "enum": ["knee", "back", "hip", "shoulder", "hands", "ankle", "neck"]}
    ]
    assert body["question_text_en"] == "Which joint hurts the most?" and body["language"] == "hi"
    assert b'name="language"' in asr.calls.last.request.content
    fact = db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "site")).one()
    assert fact.patient_words == "घुटने में दर्द है" and fact.text_en == "Site: Knee"
    assert len(list(tmp_path.rglob("*.m4a"))) == 1
    assert audit.verify_chain(db)[0]


@respx.mock
@pytest.mark.parametrize(
    ("asr_conf", "extract"),
    [
        (0.4, {"slots": {"site": "knee"}, "status": "confident", "notes": []}),  # low ASR confidence
        (0.85, {"slots": {"site": None}, "status": "uncertain", "notes": ["unclear"]}),  # extractor unsure
        (0.85, {"slots": {"site": "elbow"}, "status": "confident", "notes": []}),  # value not a choice
    ],
)
def test_uncertain_returns_same_question(client: TestClient, db: Session, asr_conf, extract) -> None:
    sid = session(client)
    respx.post(f"{NLP}/asr").mock(
        return_value=httpx.Response(200, json={"text": "umm", "confidence": asr_conf, "duration_sec": 1.0})
    )
    respx.post(f"{NLP}/extract").mock(return_value=httpx.Response(200, json=extract))
    res = speak(client, sid, "jp_site").json()
    assert res["answer"]["status"] == "uncertain"
    assert res["next"]["done"] is False and res["next"]["question"]["id"] == "jp_site"
    assert [c["value"] for c in res["fallback_choices"]][:2] == ["knee", "back"]
    assert res["fallback_choices"][0]["label"] == "घुटना"
    assert db.exec(select(Fact).where(Fact.session_id == sid, Fact.key == "site")).first() is None
    # the uncertain answer doesn't count: next-question is still jp_site
    assert client.get(f"/api/sessions/{sid}/next-question", headers=K).json()["question"]["id"] == "jp_site"


@respx.mock
def test_yesno_fallback_is_synthesised(client: TestClient) -> None:
    sid = session(client)
    respx.post(f"{NLP}/asr").mock(
        return_value=httpx.Response(200, json={"text": "", "confidence": 0.0, "duration_sec": 0.5})
    )
    respx.post(f"{NLP}/extract").mock(
        return_value=httpx.Response(200, json={"slots": {"swelling": None}, "status": "uncertain", "notes": []})
    )
    res = speak(client, sid, "jp_swelling").json()
    assert [c["value"] for c in res["fallback_choices"]] == [True, False]


@respx.mock
@pytest.mark.parametrize("failure", ["connect", "503", "extract_500"])
def test_nlp_down_is_503(client: TestClient, db: Session, failure) -> None:
    sid = session(client)
    if failure == "connect":
        respx.post(f"{NLP}/asr").mock(side_effect=httpx.ConnectError("down"))
    elif failure == "503":
        respx.post(f"{NLP}/asr").mock(return_value=httpx.Response(503, json={"error": {"code": "model_loading"}}))
    else:
        respx.post(f"{NLP}/asr").mock(
            return_value=httpx.Response(200, json={"text": "x", "confidence": 0.9, "duration_sec": 1})
        )
        respx.post(f"{NLP}/extract").mock(return_value=httpx.Response(500))
    res = speak(client, sid, "jp_site")
    assert res.status_code == 503 and res.json()["error"]["code"] == "nlp_unavailable"
    assert db.exec(select(Answer).where(Answer.source == "voice")).first() is None


def test_bad_uploads(client: TestClient) -> None:
    sid = session(client)
    assert speak(client, sid, "jp_site", "x.exe", "application/octet-stream").status_code == 422
    assert speak(client, sid, "nope").status_code == 404
    res = client.post(
        f"/api/sessions/{sid}/answers/audio",
        headers=K,
        data={"question_id": "jp_site", "language": "hi"},
        files={"audio": ("a.wav", b"", "audio/wav")},
    )
    assert res.status_code == 422
