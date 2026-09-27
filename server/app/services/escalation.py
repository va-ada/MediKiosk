"""Escalate emergency/urgent alerts nobody has acknowledged within ESCALATE_AFTER_SEC."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session as DB
from sqlmodel import select

from app import audit, db
from app.config import settings
from app.enums import AlertStatus
from app.ids import as_utc, utcnow
from app.models import Alert
from app.services.serialize import alert_public
from app.ws import hub

INTERVAL_SEC = 10


def escalate_once(session: DB, now: datetime | None = None) -> list[dict[str, Any]]:
    """Mark overdue open alerts escalated; commits and returns their Alert payloads."""
    now = now or utcnow()
    cutoff = now - timedelta(seconds=settings.escalate_after_sec)
    overdue = [
        a
        for a in session.exec(select(Alert).where(Alert.status == AlertStatus.open, Alert.escalated == False))
        if as_utc(a.created_at) <= cutoff
    ]
    for a in overdue:
        a.escalated = True
        session.add(a)
        audit.record(
            session,
            "system",
            "alert.escalate",
            "alert",
            a.id,
            {"level": a.level, "after_sec": settings.escalate_after_sec},
        )
    session.commit()
    return [alert_public(a) for a in overdue]


def _tick() -> list[dict[str, Any]]:
    with DB(db.engine) as session:
        return escalate_once(session)


async def run_forever() -> None:
    while True:
        try:
            for payload in await asyncio.to_thread(_tick):
                await hub.publish_many(["alerts", "admin"], "alert.updated", payload)
        except Exception as exc:  # noqa: BLE001  keep the safety loop alive whatever happens
            print(f"[escalation] tick failed: {exc!r}")
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
