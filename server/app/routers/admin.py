import asyncio
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import col, select

from app import audit
from app.auth import current_staff
from app.config import settings
from app.db import DbSession
from app.models import Outbox, Setting, Staff
from app.services import outbox
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
