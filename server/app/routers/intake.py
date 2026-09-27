from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from app import audit
from app.auth import kiosk_id
from app.config import settings
from app.db import DbSession
from app.enums import Language, SessionStatus
from app.errors import ApiError
from app.ids import iso_z, new_id
from app.models import Answer, Patient, Session
from app.routers.sessions import get_session_or_404
from app.services import graph, serialize
from app.services.files import store_file

router = APIRouter(prefix="/api/sessions", tags=["intake"])

KioskId = Annotated[str, Depends(kiosk_id)]
ANSWERABLE = {SessionStatus.triaged, SessionStatus.history, SessionStatus.documents, SessionStatus.verifying}


class AnswerIn(BaseModel):
    question_id: str
    source: Literal["tap", "staff"] = "tap"
    value: Any


def answer_public(a: Answer) -> dict[str, Any]:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "question_id": a.question_id,
        "source": a.source,
        "raw_text": a.raw_text,
        "confidence": a.confidence,
        "slots": a.slots,
        "status": a.status,
        "created_at": iso_z(a.created_at),
    }


def language_for(db: DbSession, s: Session, language: str | None) -> str:
    if language:
        return language
    patient = db.get(Patient, s.patient_id)
    return patient.language if patient else "hi"


def next_response(db: DbSession, s: Session, language: str) -> dict[str, Any]:
    """`{"done": false, "question": …}` or `{"done": true}`; finishing the history moves the session to documents."""
    found = graph.next_question(db, s)
    if found is None:
        if s.status in (SessionStatus.triaged, SessionStatus.history):
            s.status = SessionStatus.documents.value
            db.add(s)
            db.commit()
        return {"done": True}
    question, progress = found
    return {"done": False, "question": graph.render(question, language, progress)}


def require_answerable(s: Session) -> None:
    if s.status not in {x.value for x in ANSWERABLE}:
        raise ApiError(409, "invalid_state", f"Session is {s.status}; history can't be answered now")


def question_for(s: Session, question_id: str) -> dict[str, Any]:
    for p in graph.session_pathways(s):
        if question_id in p.questions:
            return p.questions[question_id]
    raise ApiError(404, "not_found", f"Question {question_id} is not part of this session")


@router.get("/{session_id}/next-question")
def get_next_question(
    session_id: str, db: DbSession, _kiosk: KioskId, language: Annotated[Language | None, Query()] = None
) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    require_answerable(s)
    return next_response(db, s, language_for(db, s, language.value if language else None))


@router.post("/{session_id}/answers")
def post_answer(
    session_id: str,
    body: AnswerIn,
    db: DbSession,
    kiosk: KioskId,
    language: Annotated[Language | None, Query()] = None,
) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    require_answerable(s)
    question = question_for(s, body.question_id)
    answer, alerts = graph.apply_answer(db, s, question, body.value, body.source, actor=f"kiosk:{kiosk}")
    db.refresh(s)
    return {
        "answer": answer_public(answer),
        "next": next_response(db, s, language_for(db, s, language.value if language else None)),
        "alerts": [serialize.alert_public(a) for a in alerts],
    }


# ---------------------------------------------------------------- voice answers (S7)

AUDIO_EXT = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "video/mp4": "mp4",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
}
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MIN_ASR_CONFIDENCE = 0.6
NLP_TIMEOUT_SEC = 30


def _audio_ext(upload: UploadFile) -> str:
    name_ext = (upload.filename or "").rsplit(".", 1)[-1].lower() if "." in (upload.filename or "") else ""
    if name_ext in {"webm", "ogg", "m4a", "mp4", "wav"}:
        return name_ext
    ext = AUDIO_EXT.get((upload.content_type or "").split(";")[0].strip().lower())
    if not ext:
        raise ApiError(422, "validation_error", "Audio must be webm, ogg, m4a, mp4 or wav")
    return ext


def fallback_choices(question: dict[str, Any], language: str) -> list[dict[str, Any]]:
    """Tap buttons for "Did you mean…?". Yes/no questions get synthesised yes/no choices."""
    rendered = graph.render(question, language)["choices"]
    if rendered or question["type"] != "yesno":
        return rendered
    return [
        {"value": True, "label": "हाँ" if language == "hi" else "Yes", "en": "Yes", "hi": "हाँ", "icon": "yes"},
        {"value": False, "label": "नहीं" if language == "hi" else "No", "en": "No", "hi": "नहीं", "icon": "no"},
    ]


def _nlp(client: httpx.Client, method: str, path: str, **kw: Any) -> dict[str, Any]:
    try:
        res = client.request(method, f"{settings.nlp_url}{path}", timeout=NLP_TIMEOUT_SEC, **kw)
    except httpx.HTTPError as exc:
        raise ApiError(503, "nlp_unavailable", "Speech service is not reachable — please tap your answer") from exc
    if res.status_code != 200:
        raise ApiError(503, "nlp_unavailable", f"Speech service error {res.status_code} — please tap your answer")
    return res.json()


@router.post("/{session_id}/answers/audio")
def post_audio_answer(
    session_id: str,
    db: DbSession,
    kiosk: KioskId,
    question_id: Annotated[str, Form()],
    language: Annotated[Language, Form()],
    audio: Annotated[UploadFile, File()],
) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    require_answerable(s)
    question = question_for(s, question_id)
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise ApiError(422, "validation_error", "Empty audio")
    if len(data) > MAX_AUDIO_BYTES:
        raise ApiError(413, "too_large", "Audio is larger than 10 MB")
    ext = _audio_ext(audio)
    store_file(s.patient_id, f"audio/{s.id}/{new_id()}.{ext}", data)

    slot = question["slot"]
    slot_spec: dict[str, Any] = {"name": slot["name"], "type": slot["type"]}
    if question.get("choices"):
        slot_spec["enum"] = [c["value"] for c in question["choices"]]
    with httpx.Client() as client:
        asr = _nlp(
            client,
            "POST",
            "/asr",
            files={"audio": (f"answer.{ext}", data, audio.content_type or "")},
            data={"language": language.value},
        )
        text = str(asr.get("text") or "").strip()
        confidence = float(asr.get("confidence") or 0.0)
        extracted = _nlp(
            client,
            "POST",
            "/extract",
            json={
                "question_id": question["id"],
                "language": language.value,
                "text": text,
                "question_text_en": question["text_en"],
                "slots": [slot_spec],
            },
        )

    value = (extracted.get("slots") or {}).get(slot["name"])
    confident = extracted.get("status") == "confident" and confidence >= MIN_ASR_CONFIDENCE and value is not None
    if confident:
        try:
            answer, alerts = graph.apply_answer(
                db, s, question, value, "voice", raw_text=text, confidence=confidence, actor=f"kiosk:{kiosk}"
            )
        except ApiError:
            confident = False  # the model's value doesn't fit the question: ask the patient to tap instead
    if not confident:
        answer = Answer(
            session_id=s.id,
            question_id=question["id"],
            source="voice",
            raw_text=text,
            confidence=confidence,
            slots={slot["name"]: value},
            status="uncertain",
        )
        db.add(answer)
        db.flush()
        audit.record(
            db,
            f"kiosk:{kiosk}",
            "answer.create",
            "answer",
            answer.id,
            {
                "session_id": s.id,
                "question_id": question["id"],
                "source": "voice",
                "status": "uncertain",
                "notes": extracted.get("notes") or [],
            },
        )
        db.commit()
        db.refresh(answer)
        found = graph.next_question(db, s)
        progress = found[1] if found else None
        return {
            "answer": answer_public(answer),
            "next": {"done": False, "question": graph.render(question, language.value, progress)},
            "alerts": [],
            "fallback_choices": fallback_choices(question, language.value),
        }
    db.refresh(s)
    return {
        "answer": answer_public(answer),
        "next": next_response(db, s, language.value),
        "alerts": [serialize.alert_public(a) for a in alerts],
        "fallback_choices": [],
    }
