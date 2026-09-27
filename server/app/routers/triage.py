from functools import lru_cache
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import select

from app import audit
from app.auth import kiosk_id
from app.config import settings
from app.db import DbSession
from app.enums import AnswerSource, AnswerStatus, ComplaintCode, Section, SessionStatus, SourceType, Trust
from app.errors import ApiError
from app.models import Alert, Answer, Fact
from app.routers.sessions import get_session_or_404, session_public
from app.services import redflags, serialize, tokens
from app.ws import hub

router = APIRouter(prefix="/api/sessions", tags=["triage"])

KioskId = Annotated[str, Depends(kiosk_id)]


class RedFlagsIn(BaseModel):
    chest_pain: bool
    breathless: bool
    stroke_signs: bool
    heavy_bleeding: bool
    fainted: bool


class TriageIn(BaseModel):
    complaint_code: ComplaintCode
    complaint_text: str | None = Field(default=None, max_length=500)
    body_part: str | None = Field(default=None, max_length=40)
    redflags: RedFlagsIn


@lru_cache
def triage_config() -> dict[str, Any]:
    """content/triage.yaml (§9.2), keyed by complaint code."""
    doc = yaml.safe_load((settings.content_dir / "triage.yaml").read_text(encoding="utf-8"))
    return {c["code"]: c for c in doc["complaints"]}


def _response(db: DbSession, session_id: str) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    token = tokens.latest_token(db, s.id)
    alerts = db.exec(select(Alert).where(Alert.session_id == s.id).order_by(Alert.created_at)).all()  # type: ignore[arg-type]
    return {
        "session": session_public(s),
        "token": serialize.queue_item(db, token) if token else None,
        "alerts": [serialize.alert_public(a) for a in alerts],
    }


@router.post("/{session_id}/triage")
def triage(session_id: str, body: TriageIn, db: DbSession, kiosk: KioskId) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    if tokens.latest_token(db, s.id) is not None:
        return _response(db, s.id)  # retry after a lost response: never issue a second token
    if s.status != SessionStatus.consented:
        raise ApiError(409, "consent_required", "Consent must be recorded before triage")

    complaint = triage_config().get(body.complaint_code.value)
    if complaint is None:
        raise ApiError(422, "validation_error", f"Complaint {body.complaint_code.value} is not configured")
    actor = f"kiosk:{kiosk}"
    body_part = (body.body_part or "").strip() or None
    patient_words = (body.complaint_text or "").strip() or None
    slots: dict[str, Any] = {**body.redflags.model_dump(), "complaint_code": body.complaint_code.value}
    if body_part:
        slots["body_part"] = body_part

    answer = Answer(
        session_id=s.id,
        question_id="triage",
        source=AnswerSource.tap.value,
        raw_text=patient_words,
        slots=slots,
        status=AnswerStatus.confident.value,
    )
    db.add(answer)
    db.flush()
    fact = Fact(
        session_id=s.id,
        patient_id=s.patient_id,
        section=Section.complaint.value,
        key="chief_complaint",
        value={"complaint_code": body.complaint_code.value, "body_part": body_part},
        text_en=complaint["en"],
        patient_words=patient_words,
        trust=Trust.patient_said.value,
        source_type=SourceType.answer.value,
        source_id=answer.id,
    )
    db.add(fact)

    s.complaint_code = body.complaint_code.value
    s.department = complaint["department"]
    s.pathway = complaint.get("pathway")
    s.status = SessionStatus.triaged.value
    db.add(s)
    token = tokens.issue_token(db, s, s.department)
    audit.record(
        db,
        actor,
        "session.triage",
        "session",
        s.id,
        {"complaint_code": s.complaint_code, "department": s.department, "redflags": body.redflags.model_dump()},
    )
    audit.record(db, actor, "token.create", "token", token.id, {"display": token.display, "lane": token.lane})
    redflags.evaluate_and_alert(db, s, slots)
    db.commit()

    result = _response(db, s.id)
    hub.emit(["queue", "display"], "token.created", result["token"])
    return result
