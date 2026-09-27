from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app import audit
from app.auth import check_pin, create_jwt
from app.db import DbSession
from app.errors import ApiError
from app.models import Staff

router = APIRouter(prefix="/api/staff", tags=["staff"])


class LoginIn(BaseModel):
    staff_id: str
    pin: str


def staff_public(staff: Staff) -> dict[str, Any]:
    return {"id": staff.id, "name": staff.name, "role": staff.role, "department": staff.department, "room": staff.room}


@router.post("/login")
def login(body: LoginIn, db: DbSession) -> dict[str, Any]:
    staff = db.get(Staff, body.staff_id.strip().upper())
    if staff is None or not staff.active or not check_pin(body.pin, staff.pin_hash):
        # Same error whether the id or the PIN is wrong: don't reveal which staff ids exist.
        audit.record(db, "system", "staff.login_failed", "staff", body.staff_id[:32], {})
        db.commit()
        raise ApiError(401, "invalid_pin", "Wrong staff ID or PIN")
    audit.record(db, f"staff:{staff.id}", "staff.login", "staff", staff.id, {"role": staff.role})
    db.commit()
    return {"token": create_jwt(staff), "staff": staff_public(staff)}
