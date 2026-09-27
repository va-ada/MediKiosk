from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app import audit
from app.auth import current_staff, kiosk_id
from app.db import DbSession
from app.enums import SessionStatus
from app.errors import ApiError
from app.ids import utcnow
from app.models import Staff
from app.routers.sessions import get_session_or_404, session_public
from app.services import summary
from app.ws import hub

router = APIRouter(prefix="/api/sessions", tags=["summary"])

SUBMITTABLE = {SessionStatus.triaged, SessionStatus.history, SessionStatus.documents, SessionStatus.verifying}
Doctor = Annotated[Staff, Depends(current_staff(["doctor"]))]


def rebuild(db: DbSession, s: Any, actor: str) -> Any:
    """Store a new summary version if anything changed, commit, and announce it. Used by S14 too."""
    row, is_new = summary.store_if_changed(db, s)
    if is_new:
        audit.record(db, actor, "summary.build", "summary", row.id, {"session_id": s.id, "version": row.version})
    db.commit()
    if is_new:
        hub.emit("queue", "summary.ready", {"session_id": s.id, "version": row.version})
    return row


@router.post("/{session_id}/submit")
def submit(session_id: str, db: DbSession, kiosk: Annotated[str, Depends(kiosk_id)]) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    if s.status not in {x.value for x in SUBMITTABLE} | {SessionStatus.submitted.value}:
        raise ApiError(409, "invalid_state", f"Session is {s.status}; it can't be submitted now")
    if s.status != SessionStatus.submitted:
        s.status, s.submitted_at = SessionStatus.submitted.value, utcnow()
        db.add(s)
        audit.record(db, f"kiosk:{kiosk}", "session.submit", "session", s.id, {})
    row = rebuild(db, s, f"kiosk:{kiosk}")
    db.refresh(s)
    return {"session": session_public(s), "summary_version": row.version}


@router.get("/{session_id}/summary")
def get_summary(session_id: str, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    if s.opened_by_doctor_at is None:
        s.opened_by_doctor_at = utcnow()
        if s.status != SessionStatus.closed:
            s.status = SessionStatus.with_doctor.value
        db.add(s)
        audit.record(db, f"staff:{doctor.id}", "session.open", "session", s.id, {})
    row = rebuild(db, s, f"staff:{doctor.id}")
    return summary.public(row)
