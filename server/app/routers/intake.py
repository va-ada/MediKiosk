from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth import kiosk_id
from app.db import DbSession
from app.enums import Language, SessionStatus
from app.errors import ApiError
from app.ids import iso_z
from app.models import Answer, Patient, Session
from app.routers.sessions import get_session_or_404
from app.services import graph, serialize

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
