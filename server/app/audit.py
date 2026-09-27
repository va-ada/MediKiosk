"""Hash-chained audit log (CONTRACTS.md §10.7).

hash = sha256_hex(prev_hash + canonical_json({ts, actor, action, entity, entity_id, details}))

`record()` adds and flushes the row but does not commit: the caller commits it together with the
change it describes, so an entity change and its audit row land atomically.
"""

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, col, select

from app.ids import iso_z, utcnow
from app.models import AuditLog

GENESIS = "0" * 64


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(
    prev_hash: str, ts: datetime, actor: str, action: str, entity: str, entity_id: str | None, details: dict
) -> str:
    body = {
        "ts": iso_z(ts),
        "actor": actor,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "details": details,
    }
    return hashlib.sha256((prev_hash + canonical_json(body)).encode("utf-8")).hexdigest()


def _lock_chain(db: Session) -> None:
    """Serialise chain appends across connections (Postgres only; SQLite tests are single-writer)."""
    if db.get_bind().dialect.name == "postgresql":
        db.exec(text("SELECT pg_advisory_xact_lock(74656)"))  # type: ignore[call-overload]


def record(
    db: Session, actor: str, action: str, entity: str, entity_id: str | None, details: dict[str, Any] | None = None
) -> AuditLog:
    """Append one audit row. `actor` is `kiosk:<id>`, `staff:<id>` or `system`."""
    _lock_chain(db)
    details = json.loads(canonical_json(details or {}))  # store exactly what was hashed
    last = db.exec(select(AuditLog).order_by(col(AuditLog.id).desc()).limit(1)).first()
    prev_hash = last.hash if last else GENESIS
    ts = utcnow()
    row = AuditLog(
        ts=ts,
        actor=actor,
        action=action,
        entity=entity,
        entity_id=entity_id,
        details=details,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, ts, actor, action, entity, entity_id, details),
    )
    db.add(row)
    db.flush()
    return row


def verify_chain(db: Session) -> tuple[bool, int, int | None]:
    """Walk the chain oldest-first. Returns (valid, checked, first_bad_id)."""
    expected_prev = GENESIS
    checked = 0
    for row in db.exec(select(AuditLog).order_by(col(AuditLog.id))):
        checked += 1
        recomputed = compute_hash(row.prev_hash, row.ts, row.actor, row.action, row.entity, row.entity_id, row.details)
        if row.prev_hash != expected_prev or row.hash != recomputed:
            return False, checked, row.id
        expected_prev = row.hash
    return True, checked, None


def to_dict(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": iso_z(row.ts),
        "actor": row.actor,
        "action": row.action,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "details": row.details,
        "prev_hash": row.prev_hash,
        "hash": row.hash,
    }
