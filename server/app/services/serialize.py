"""Wire shapes shared by several routers (CONTRACTS.md §11)."""

from typing import Any

from sqlmodel import Session as DB
from sqlmodel import col, select

from app.config import settings
from app.enums import AlertStatus, Lane, TokenStatus
from app.ids import as_utc, iso_z, utcnow
from app.models import Alert, Fact, Patient, Staff, Token

ACTIVE_ALERT = (AlertStatus.open.value, AlertStatus.acknowledged.value, AlertStatus.confirmed.value)


def wait_minutes(token: Token) -> int:
    return max(0, int((utcnow() - as_utc(token.created_at)).total_seconds() // 60))


def complaint_label(db: DB, session_id: str) -> str | None:
    fact = db.exec(select(Fact).where(Fact.session_id == session_id, Fact.key == "chief_complaint")).first()
    return fact.text_en if fact else None


def token_flags(db: DB, token: Token, wait_min: int) -> list[str]:
    flags: list[str] = []
    has_alert = db.exec(
        select(Alert.id).where(Alert.session_id == token.session_id, col(Alert.status).in_(ACTIVE_ALERT))
    ).first()
    if has_alert:
        flags.append("red_flag")
    if token.lane == Lane.normal and token.status == TokenStatus.waiting and wait_min >= settings.wait_limit_min:
        flags.append("aged")
    if token.preferred_doctor_id:
        flags.append("recheck")
    was_referred = db.exec(
        select(Token.id).where(
            Token.arrival_seq == token.arrival_seq, Token.id != token.id, Token.status == TokenStatus.referred
        )
    ).first()
    if was_referred:
        flags.append("referred")
    return flags


def queue_item(db: DB, token: Token) -> dict[str, Any]:
    """QueueItem (§11.2)."""
    patient = db.get(Patient, token.patient_id)
    doctor = db.get(Staff, token.doctor_id) if token.doctor_id else None
    wait = wait_minutes(token)
    return {
        "id": token.id,
        "display": token.display,
        "lane": token.lane,
        "status": token.status,
        "department": token.department,
        "session_id": token.session_id,
        "patient": {"name": patient.name, "age": patient.age, "sex": patient.sex, "language": patient.language}
        if patient
        else None,
        "complaint": complaint_label(db, token.session_id),
        "arrival_seq": token.arrival_seq,
        "created_at": iso_z(token.created_at),
        "wait_min": wait,
        "flags": token_flags(db, token, wait),
        "called_count": token.called_count,
        "doctor_id": token.doctor_id,
        "doctor_name": doctor.name if doctor else None,
        "preferred_doctor_id": token.preferred_doctor_id,
    }


def alert_public(a: Alert) -> dict[str, Any]:
    """Alert (§11.3)."""
    return {
        "id": a.id,
        "kiosk_id": a.kiosk_id,
        "session_id": a.session_id,
        "level": a.level,
        "reason_code": a.reason_code,
        "rule_id": a.rule_id,
        "reason_text": a.reason_text,
        "source": a.source,
        "status": a.status,
        "escalated": a.escalated,
        "created_at": iso_z(a.created_at),
        "acknowledged_by": a.acknowledged_by,
        "acknowledged_at": iso_z(a.acknowledged_at),
        "resolved_by": a.resolved_by,
        "resolved_at": iso_z(a.resolved_at),
    }
