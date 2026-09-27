from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app import audit
from app.auth import current_staff, kiosk_id
from app.db import DbSession
from app.enums import AlertLevel, AlertSource, AlertStatus, Lane, ReasonCode, TokenStatus
from app.errors import ApiError
from app.ids import utcnow
from app.models import Alert, Session, Staff
from app.services import escalation, serialize, tokens
from app.ws import hub

router = APIRouter(prefix="/api/alerts", tags=["alerts"], lifespan=escalation.lifespan)

NurseOrDoctor = Annotated[Staff, Depends(current_staff(["nurse", "doctor"]))]
REASON_LABEL = {
    "chest_pain": "chest pain",
    "breathing": "breathing difficulty",
    "bleeding": "bleeding",
    "unconscious": "unconscious",
    "seizure": "seizure",
    "stroke_signs": "stroke signs",
    "severe_pain": "severe pain",
    "pregnancy": "pregnancy emergency",
    "other": "other",
}


class EmergencyIn(BaseModel):
    id: str = Field(min_length=8, max_length=64)
    kiosk_id: str | None = Field(default=None, max_length=40)
    reason_code: ReasonCode
    session_id: str | None = None


class ResolveIn(BaseModel):
    outcome: Literal["confirmed", "downgraded"]


def _alert(db: DbSession, alert_id: str) -> Alert:
    a = db.get(Alert, alert_id)
    if a is None:
        raise ApiError(404, "not_found", "Alert not found")
    return a


@router.post("/emergency")
def emergency(body: EmergencyIn, db: DbSession, kiosk: Annotated[str, Depends(kiosk_id)]) -> dict[str, Any]:
    """Emergency button. Idempotent on the client-generated id; never fails on an unknown session."""
    existing = db.get(Alert, body.id)
    if existing:
        return serialize.alert_public(existing)
    session_id = body.session_id if body.session_id and db.get(Session, body.session_id) else None
    a = Alert(
        id=body.id,
        kiosk_id=body.kiosk_id or kiosk,
        session_id=session_id,
        level=AlertLevel.emergency.value,
        reason_code=body.reason_code.value,
        reason_text=f"Emergency button: {REASON_LABEL[body.reason_code.value]}",
        source=AlertSource.button.value,
        status=AlertStatus.open.value,
    )
    db.add(a)
    db.flush()
    audit.record(
        db,
        f"kiosk:{kiosk}",
        "alert.create",
        "alert",
        a.id,
        {"reason_code": a.reason_code, "session_id": session_id, "source": "button"},
    )
    db.commit()
    payload = serialize.alert_public(a)
    hub.emit(["alerts", "admin"], "alert.created", payload)
    return payload


@router.get("")
def list_alerts(
    db: DbSession,
    _staff: NurseOrDoctor,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict[str, Any]]:
    q = select(Alert)
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        bad = [s for s in wanted if s not in {x.value for x in AlertStatus}]
        if bad:
            raise ApiError(422, "validation_error", f"Unknown alert status: {', '.join(bad)}")
        q = q.where(col(Alert.status).in_(wanted))
    return [serialize.alert_public(a) for a in db.exec(q.order_by(col(Alert.created_at).desc()).limit(limit))]


@router.post("/{alert_id}/ack")
def ack(alert_id: str, db: DbSession, staff: NurseOrDoctor) -> dict[str, Any]:
    a = _alert(db, alert_id)
    if a.status == AlertStatus.acknowledged:
        return serialize.alert_public(a)
    if a.status != AlertStatus.open:
        raise ApiError(409, "invalid_state", f"Alert is already {a.status}")
    a.status, a.acknowledged_by, a.acknowledged_at = AlertStatus.acknowledged.value, staff.id, utcnow()
    db.add(a)
    audit.record(db, f"staff:{staff.id}", "alert.ack", "alert", a.id, {})
    db.commit()
    payload = serialize.alert_public(a)
    hub.emit(["alerts", "admin"], "alert.updated", payload)
    return payload


@router.post("/{alert_id}/resolve")
def resolve(alert_id: str, body: ResolveIn, db: DbSession, staff: NurseOrDoctor) -> dict[str, Any]:
    a = _alert(db, alert_id)
    if a.status not in (AlertStatus.open, AlertStatus.acknowledged):
        raise ApiError(409, "invalid_state", f"Alert is already {a.status}")
    now = utcnow()
    a.status, a.resolved_by, a.resolved_at = body.outcome, staff.id, now
    if a.acknowledged_at is None:
        a.acknowledged_by, a.acknowledged_at = staff.id, now
    db.add(a)
    token = tokens.latest_token(db, a.session_id) if a.session_id else None
    lane_change = None
    if token and token.status in (TokenStatus.waiting, TokenStatus.called):
        # confirmed → emergency lane; downgraded → normal lane, keeping arrival_seq (place in line)
        new_lane = Lane.emergency.value if body.outcome == "confirmed" else Lane.normal.value
        lane_change = {"token_id": token.id, "from": token.lane, "to": new_lane}
        token.lane = new_lane
        db.add(token)
    audit.record(
        db, f"staff:{staff.id}", "alert.resolve", "alert", a.id, {"outcome": body.outcome, "lane_change": lane_change}
    )
    db.commit()
    payload = serialize.alert_public(a)
    hub.emit(["alerts", "admin"], "alert.updated", payload)
    if token and lane_change:
        hub.emit(["queue", "display"], "token.updated", serialize.queue_item(db, token))
    return payload
