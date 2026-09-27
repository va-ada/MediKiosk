from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session as DB

from app import audit
from app.auth import kiosk_id, kiosk_or_staff
from app.db import DbSession
from app.enums import Informant, LegalBasis, SessionStatus
from app.errors import ApiError
from app.ids import iso_z
from app.models import Consent, Patient, Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

KioskId = Annotated[str, Depends(kiosk_id)]


class SessionCreateIn(BaseModel):
    patient_id: str
    informant: Informant
    informant_relation: str | None = Field(default=None, max_length=40)


class ConsentIn(BaseModel):
    capture: bool
    scan: bool
    share_hospital: bool
    link_abha: bool
    check_passed: bool


def session_public(s: Session) -> dict[str, Any]:
    return {
        "id": s.id,
        "patient_id": s.patient_id,
        "kiosk_id": s.kiosk_id,
        "informant": s.informant,
        "informant_relation": s.informant_relation,
        "status": s.status,
        "legal_basis": s.legal_basis,
        "complaint_code": s.complaint_code,
        "pathway": s.pathway,
        "department": s.department,
        "created_at": iso_z(s.created_at),
        "submitted_at": iso_z(s.submitted_at),
        "opened_by_doctor_at": iso_z(s.opened_by_doctor_at),
        "closed_at": iso_z(s.closed_at),
    }


def consent_public(c: Consent) -> dict[str, Any]:
    return {
        "id": c.id,
        "session_id": c.session_id,
        "capture": c.capture,
        "scan": c.scan,
        "share_hospital": c.share_hospital,
        "link_abha": c.link_abha,
        "check_passed": c.check_passed,
        "created_at": iso_z(c.created_at),
        "revoked_at": iso_z(c.revoked_at),
    }


def get_session_or_404(db: DB, session_id: str) -> Session:
    s = db.get(Session, session_id)
    if s is None:
        raise ApiError(404, "not_found", "Session not found")
    return s


@router.post("")
def create_session(body: SessionCreateIn, db: DbSession, kiosk: KioskId) -> dict[str, Any]:
    if db.get(Patient, body.patient_id) is None:
        raise ApiError(404, "not_found", "Patient not found")
    relation = (body.informant_relation or "").strip() or None
    s = Session(
        patient_id=body.patient_id,
        kiosk_id=kiosk,
        informant=body.informant.value,
        informant_relation=relation if body.informant == Informant.proxy else None,
        status=SessionStatus.identifying.value,
        legal_basis=LegalBasis.consent.value,
    )
    db.add(s)
    db.flush()
    audit.record(
        db,
        f"kiosk:{kiosk}",
        "session.create",
        "session",
        s.id,
        {"patient_id": s.patient_id, "informant": s.informant, "informant_relation": s.informant_relation},
    )
    db.commit()
    db.refresh(s)
    return session_public(s)


@router.get("/{session_id}")
def get_session(session_id: str, db: DbSession, _actor: Annotated[str, Depends(kiosk_or_staff)]) -> dict[str, Any]:
    return session_public(get_session_or_404(db, session_id))


@router.post("/{session_id}/consent")
def give_consent(session_id: str, body: ConsentIn, db: DbSession, kiosk: KioskId) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    c = Consent(session_id=s.id, **body.model_dump())
    db.add(c)
    if s.status == SessionStatus.identifying:  # re-consent later in the flow never moves status backwards
        s.status = SessionStatus.consented.value
        db.add(s)
    db.flush()
    audit.record(db, f"kiosk:{kiosk}", "consent.create", "consent", c.id, {"session_id": s.id, **body.model_dump()})
    db.commit()
    db.refresh(c)
    return consent_public(c)
