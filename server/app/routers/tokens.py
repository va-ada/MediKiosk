import importlib.util
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session as DB
from sqlmodel import select

from app import audit
from app.auth import current_staff, kiosk_or_staff
from app.db import DbSession
from app.enums import Department, Lane, Outcome, SessionStatus, TokenStatus
from app.errors import ApiError
from app.ids import today_ist, utcnow
from app.models import Session, Staff, Token
from app.routers.queue import called_payload
from app.services import queue, serialize, tokens
from app.ws import hub

router = APIRouter(tags=["tokens"])

Doctor = Annotated[Staff, Depends(current_staff(["doctor"]))]


class OutcomeIn(BaseModel):
    outcome: Outcome
    refer_department: Department | None = None
    followup_date: date | None = None
    results_tomorrow: bool = False
    admit: bool = False
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _required_fields(self) -> "OutcomeIn":
        if self.outcome == Outcome.refer and self.refer_department is None:
            raise ValueError("refer needs refer_department")
        if self.outcome == Outcome.followup and self.followup_date is None:
            raise ValueError("followup needs followup_date")
        return self


def _token(db: DB, token_id: str) -> Token:
    t = db.get(Token, token_id)
    if t is None:
        raise ApiError(404, "not_found", "Token not found")
    return t


def _require(t: Token, *statuses: TokenStatus) -> None:
    if t.status not in {s.value for s in statuses}:
        raise ApiError(409, "invalid_state", f"Token {t.display} is {t.status}")


def _not_other_doctors(t: Token, doctor: Staff) -> None:
    if t.status == TokenStatus.in_ and t.doctor_id not in (None, doctor.id):
        raise ApiError(409, "already_in", f"Token {t.display} is with another doctor")


def _updated(db: DB, t: Token) -> dict[str, Any]:
    item = serialize.queue_item(db, t)
    hub.emit(["queue", "display"], "token.updated", item)
    return item


def _enqueue_bundle(db: DB, session: Session) -> None:
    if importlib.util.find_spec("app.services.fhir") is None:
        return  # TODO(S15): FHIR bundle builder not built yet
    from app.services import fhir  # type: ignore[attr-defined]

    fhir.enqueue_bundle(db, session)


@router.post("/api/tokens/{token_id}/call")
def call(token_id: str, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    t = _token(db, token_id)
    _require(t, TokenStatus.waiting, TokenStatus.called)
    queue.mark_called(db, t, doctor)
    audit.record(
        db, f"staff:{doctor.id}", "token.call", "token", t.id, {"display": t.display, "called_count": t.called_count}
    )
    db.commit()
    item = serialize.queue_item(db, t)
    hub.emit(["queue", "display"], "token.called", called_payload(item, doctor))
    return item


@router.post("/api/tokens/{token_id}/in")
def mark_in(token_id: str, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    t = _token(db, token_id)
    _not_other_doctors(t, doctor)
    if t.status == TokenStatus.in_:
        return serialize.queue_item(db, t)  # same doctor pressed In twice
    _require(t, TokenStatus.waiting, TokenStatus.called)
    t.status, t.doctor_id, t.in_at = TokenStatus.in_.value, doctor.id, utcnow()
    db.add(t)
    audit.record(db, f"staff:{doctor.id}", "token.in", "token", t.id, {"display": t.display})
    db.commit()
    return _updated(db, t)


@router.post("/api/tokens/{token_id}/no-show")
def no_show(token_id: str, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    t = _token(db, token_id)
    _require(t, TokenStatus.called, TokenStatus.waiting)
    t.status = TokenStatus.absent.value if t.called_count >= 2 else TokenStatus.waiting.value
    t.doctor_id = None
    db.add(t)
    audit.record(
        db,
        f"staff:{doctor.id}",
        "token.no_show",
        "token",
        t.id,
        {"display": t.display, "called_count": t.called_count, "status": t.status},
    )
    db.commit()
    return _updated(db, t)


@router.post("/api/tokens/{token_id}/reactivate")
def reactivate(token_id: str, db: DbSession, actor: Annotated[str, Depends(kiosk_or_staff)]) -> dict[str, Any]:
    t = _token(db, token_id)
    _require(t, TokenStatus.absent)
    t.status = TokenStatus.waiting.value
    db.add(t)
    audit.record(db, actor, "token.reactivate", "token", t.id, {"display": t.display})
    db.commit()
    return _updated(db, t)


@router.post("/api/tokens/{token_id}/outcome")
def outcome(token_id: str, body: OutcomeIn, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    t = _token(db, token_id)
    _not_other_doctors(t, doctor)
    _require(t, TokenStatus.in_, TokenStatus.called)
    session = db.get(Session, t.session_id)
    now = utcnow()
    note = (body.note or "").strip() or None
    if body.admit:
        note = f"Admit: yes. {note}" if note else "Admit: yes."
    t.outcome, t.outcome_note, t.doctor_id = body.outcome.value, note, doctor.id
    extra: dict[str, Any] = {}
    new_token: Token | None = None

    if body.outcome == Outcome.out:
        t.status, t.closed_at = TokenStatus.done.value, now
        if session:
            session.status, session.closed_at = SessionStatus.closed.value, now
    elif body.outcome == Outcome.followup:
        t.status, t.closed_at, t.followup_date = TokenStatus.done.value, now, body.followup_date
        if session:
            session.status, session.closed_at = SessionStatus.closed.value, now
    elif body.outcome == Outcome.recheck:
        if body.results_tomorrow and session:
            t.status, t.closed_at = TokenStatus.done.value, now
            new_token = tokens.issue_token(
                db,
                session,
                t.department,
                lane=Lane.priority.value,
                day=today_ist() + timedelta(days=1),
                preferred_doctor_id=doctor.id,
            )
        else:
            t.status, t.lane, t.preferred_doctor_id, t.doctor_id = (
                TokenStatus.waiting.value,
                Lane.priority.value,
                doctor.id,
                None,
            )
    elif body.outcome == Outcome.refer and session and body.refer_department:
        t.status, t.closed_at = TokenStatus.referred.value, now
        session.department = body.refer_department.value
        new_token = tokens.issue_token(
            db, session, body.refer_department.value, lane=Lane.priority.value, arrival_seq=t.arrival_seq
        )
    db.add(t)
    if session:
        db.add(session)
    if new_token:
        extra = {"new_token_id": new_token.id, "new_display": new_token.display, "new_day": str(new_token.day)}
    audit.record(
        db,
        f"staff:{doctor.id}",
        "token.outcome",
        "token",
        t.id,
        {
            "display": t.display,
            "outcome": body.outcome.value,
            "results_tomorrow": body.results_tomorrow,
            "refer_department": body.refer_department.value if body.refer_department else None,
            "followup_date": str(body.followup_date) if body.followup_date else None,
            "admit": body.admit,
            **extra,
        },
    )
    if body.outcome == Outcome.out and session:
        _enqueue_bundle(db, session)
    db.commit()
    item = _updated(db, t)
    if new_token:
        hub.emit(["queue", "display"], "token.created", serialize.queue_item(db, new_token))
    return item


@router.post("/api/doctors/signout")
def signout(db: DbSession, doctor: Doctor) -> dict[str, int]:
    """Release this doctor's reserved rechecks back to the shared priority lane."""
    reserved = db.exec(
        select(Token).where(Token.preferred_doctor_id == doctor.id, Token.status == TokenStatus.waiting)
    ).all()
    for t in reserved:
        t.preferred_doctor_id = None
        db.add(t)
    audit.record(db, f"staff:{doctor.id}", "doctor.signout", "staff", doctor.id, {"returned_tokens": len(reserved)})
    db.commit()
    for t in reserved:
        _updated(db, t)
    return {"returned_tokens": len(reserved)}
