from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app import audit
from app.auth import current_staff
from app.db import DbSession
from app.enums import Department
from app.ids import iso_z
from app.models import Staff
from app.services import queue, serialize
from app.ws import hub

router = APIRouter(tags=["queue"])

DoctorOrNurse = Annotated[Staff, Depends(current_staff(["doctor", "nurse"]))]
Doctor = Annotated[Staff, Depends(current_staff(["doctor"]))]


class NextIn(BaseModel):
    department: Department


def called_payload(token_item: dict[str, Any], doctor: Staff) -> dict[str, Any]:
    """`token.called` event data: QueueItem + doctor_name + room (§5)."""
    return {**token_item, "doctor_name": doctor.name, "room": doctor.room}


@router.get("/api/queue")
def get_queue(
    db: DbSession, staff: DoctorOrNurse, department: Annotated[Department | None, Query()] = None
) -> list[dict[str, Any]]:
    dept = department.value if department else staff.department  # nurses without a department see everything
    return [serialize.queue_item(db, t) for t in queue.board(db, dept)]


@router.post("/api/queue/next", response_model=None)
def queue_next(body: NextIn, db: DbSession, doctor: Doctor) -> dict[str, Any] | Response:
    token = queue.select_next(db, body.department.value, doctor.id)
    if token is None:
        return Response(status_code=204)
    queue.mark_called(db, token, doctor)
    audit.record(
        db,
        f"staff:{doctor.id}",
        "token.call",
        "token",
        token.id,
        {"display": token.display, "via": "queue_next", "called_count": token.called_count},
    )
    db.commit()
    item = serialize.queue_item(db, token)
    hub.emit(["queue", "display"], "token.called", called_payload(item, doctor))
    return item


@router.get("/api/display/state")
def display_state(db: DbSession, department: Annotated[Department | None, Query()] = None) -> dict[str, Any]:
    """Public (§11.5)."""
    dept = department.value if department else None
    serving = []
    for t in queue.now_serving(db, dept):
        doctor = db.get(Staff, t.doctor_id) if t.doctor_id else None
        serving.append(
            {
                "display": t.display,
                "doctor_name": doctor.name if doctor else None,
                "room": doctor.room if doctor else None,
                "called_at": iso_z(t.called_at),
            }
        )
    return {"department": dept, "now_serving": serving, "next": [t.display for t in queue.preview(db, dept)[:5]]}
