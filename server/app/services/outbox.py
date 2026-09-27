"""Outbox worker (CONTRACTS.md §10.6): the only way data leaves the hospital (rule 9)."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session as DB
from sqlmodel import col, select

from app import audit, db
from app.config import settings
from app.enums import OutboxStatus
from app.ids import as_utc, iso_z, utcnow
from app.models import Consent, Outbox, Setting

INTERVAL_SEC = 5
SEND_TIMEOUT_SEC = 10
MAX_BACKOFF_SEC = 300


def island_mode(session: DB) -> bool:
    row = session.get(Setting, "island_mode")
    return bool(row.value) if row else False


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(5 * 2**attempts, MAX_BACKOFF_SEC))


def consent_ok(session: DB, session_id: str) -> bool:
    """Re-checked at send time: the latest consent must still allow sharing and not be revoked."""
    c = session.exec(
        select(Consent).where(Consent.session_id == session_id).order_by(col(Consent.created_at).desc())
    ).first()
    return bool(c and c.share_hospital and c.revoked_at is None)


def drain_once(session: DB, client: httpx.Client, now: datetime | None = None) -> dict[str, int]:
    """One worker pass. Commits after every row. Returns counts by outcome."""
    counts = {"sent": 0, "retry": 0, "skipped": 0}
    if island_mode(session):
        return counts
    now = now or utcnow()
    due = [
        r
        for r in session.exec(
            select(Outbox).where(Outbox.status == OutboxStatus.pending).order_by(col(Outbox.created_at))
        )
        if as_utc(r.next_attempt_at) <= now
    ]
    for row in due:
        if island_mode(session):  # the switch can be flipped mid-drain
            break
        if not consent_ok(session, row.session_id):
            row.status = OutboxStatus.skipped_no_consent.value
            audit.record(session, "system", "outbox.skip", "outbox", row.id, {"reason": "no_consent"})
            counts["skipped"] += 1
        else:
            error = None
            try:
                res = client.post(
                    f"{settings.his_url}/fhir",
                    json=row.payload,
                    headers={"Idempotency-Key": row.idempotency_key},
                    timeout=SEND_TIMEOUT_SEC,
                )
                if not 200 <= res.status_code < 300:
                    error = f"HTTP {res.status_code}: {res.text[:200]}"
            except httpx.HTTPError as exc:
                error = f"{type(exc).__name__}: {exc}"[:300]
            if error is None:
                row.status, row.sent_at, row.last_error = OutboxStatus.sent.value, utcnow(), None
                audit.record(session, "system", "outbox.sent", "outbox", row.id, {"key": row.idempotency_key})
                counts["sent"] += 1
            else:
                row.attempts += 1
                row.last_error = error
                row.next_attempt_at = utcnow() + backoff(row.attempts)
                audit.record(
                    session,
                    "system",
                    "outbox.retry",
                    "outbox",
                    row.id,
                    {"attempts": row.attempts, "error": error[:120]},
                )
                counts["retry"] += 1
        session.add(row)
        session.commit()
    return counts


def outbox_public(row: Outbox, include_payload: bool = False) -> dict[str, Any]:
    out = {
        "id": row.id,
        "kind": row.kind,
        "session_id": row.session_id,
        "patient_id": row.patient_id,
        "idempotency_key": row.idempotency_key,
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "next_attempt_at": iso_z(row.next_attempt_at),
        "created_at": iso_z(row.created_at),
        "sent_at": iso_z(row.sent_at),
        "resource_count": len((row.payload or {}).get("entry") or []),
    }
    if include_payload:
        out["payload"] = row.payload
    return out


def _tick() -> dict[str, int]:
    with DB(db.engine) as session, httpx.Client() as client:
        return drain_once(session, client)


async def run_forever() -> None:
    while True:
        try:
            await asyncio.to_thread(_tick)
        except Exception as exc:  # noqa: BLE001  the worker must survive anything and try again
            print(f"[outbox] tick failed: {exc!r}")
        await asyncio.sleep(INTERVAL_SEC)


@asynccontextmanager
async def lifespan(_: Any) -> AsyncIterator[None]:
    if not settings.run_workers:
        yield
        return
    task = asyncio.create_task(run_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
