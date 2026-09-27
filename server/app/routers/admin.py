import asyncio
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import col, select

from app import audit
from app.auth import check_pin, current_staff
from app.config import settings
from app.db import DbSession
from app.errors import ApiError
from app.ids import iso_z
from app.models import Outbox, Patient, Setting, Staff
from app.services import crypto, outbox
from app.ws import hub

router = APIRouter(prefix="/api/admin", tags=["admin"], lifespan=outbox.lifespan)

Admin = Annotated[Staff, Depends(current_staff(["admin"]))]
PROBE_TIMEOUT_SEC = 2


class IslandIn(BaseModel):
    enabled: bool


async def _probe(client: httpx.AsyncClient, url: str) -> bool:
    try:
        return (await client.get(url, timeout=PROBE_TIMEOUT_SEC)).status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/health")
async def health(db: DbSession, _admin: Admin) -> dict[str, bool]:
    try:
        db.exec(text("SELECT 1"))  # type: ignore[call-overload]
        db_ok = True
    except Exception:  # noqa: BLE001  any DB failure just means "down"
        db_ok = False
    async with httpx.AsyncClient() as client:
        nlp, relay, his, ollama = await asyncio.gather(
            _probe(client, f"{settings.nlp_url}/health"),
            _probe(client, f"{settings.relay_url}/health"),
            _probe(client, f"{settings.his_url}/bundles"),
            _probe(client, f"{settings.ollama_url}/api/tags"),
        )
    return {
        "db": db_ok,
        "nlp": nlp,
        "relay": relay,
        "his": his,
        "ollama": ollama,
        "island_mode": outbox.island_mode(db) if db_ok else False,
    }


@router.get("/island")
def get_island(db: DbSession, _admin: Admin) -> dict[str, bool]:
    return {"enabled": outbox.island_mode(db)}


@router.post("/island")
def set_island(body: IslandIn, db: DbSession, admin: Admin) -> dict[str, bool]:
    row = db.get(Setting, "island_mode") or Setting(key="island_mode", value=False)
    before = bool(row.value)
    row.value = body.enabled
    db.add(row)
    audit.record(db, f"staff:{admin.id}", "island.set", "setting", "island_mode", {"from": before, "to": body.enabled})
    db.commit()
    hub.emit("admin", "island.changed", {"enabled": body.enabled})
    return {"enabled": body.enabled}


@router.get("/outbox")
def list_outbox(
    db: DbSession,
    _admin: Admin,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    include_payload: bool = False,
) -> list[dict[str, Any]]:
    rows = db.exec(select(Outbox).order_by(col(Outbox.created_at).desc()).limit(limit))
    return [outbox.outbox_public(r, include_payload) for r in rows]


class EraseIn(BaseModel):
    approver_staff_id: str
    approver_pin: str


@router.post("/patients/{patient_id}/erase")
def erase_patient(patient_id: str, body: EraseIn, db: DbSession, admin: Admin) -> dict[str, bool]:
    """Two-person rule: the caller (admin) plus a DIFFERENT admin's id + PIN. Destroys the patient's data key."""
    if db.get(Patient, patient_id) is None:
        raise ApiError(404, "not_found", "Patient not found")
    approver_id = body.approver_staff_id.strip().upper()
    if approver_id == admin.id:
        raise ApiError(403, "forbidden", "A second, different admin must approve erasure")
    approver = db.get(Staff, approver_id)
    if approver is None or not approver.active or not check_pin(body.approver_pin, approver.pin_hash):
        audit.record(
            db,
            f"staff:{admin.id}",
            "patient.erase_denied",
            "patient",
            patient_id,
            {"approver": approver_id[:32], "reason": "invalid_pin"},
        )
        db.commit()
        raise ApiError(401, "invalid_pin", "Approver ID or PIN is wrong")
    if approver.role != "admin":
        raise ApiError(403, "forbidden", "The approver must be an admin")
    row = crypto.destroy_key(db, patient_id)
    audit.record(
        db,
        f"staff:{admin.id}",
        "patient.erase",
        "patient",
        patient_id,
        {"approver": approver.id, "destroyed_at": iso_z(row.destroyed_at)},
    )
    db.commit()
    return {"destroyed": True}
