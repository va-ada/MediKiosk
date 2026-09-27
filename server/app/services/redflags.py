"""Red-flag rules engine (CONTRACTS.md §9.3). Rules only — never a model (rule 3).

A rule fires when ALL `all` conditions hold AND (if `any` exists) at least one `any` condition holds.
A condition on a slot that hasn't been answered fails; `false` is a real answer (`is: false` can match).
"""

from functools import lru_cache
from typing import Any

import yaml
from sqlalchemy import event
from sqlmodel import Session as DB
from sqlmodel import select

from app import audit
from app.config import settings
from app.enums import AlertSource, AlertStatus
from app.models import Alert, Session
from app.services.serialize import alert_public
from app.ws import hub

_override: list[dict[str, Any]] | None = None  # tests install inline rules here


@lru_cache
def _loaded() -> list[dict[str, Any]]:
    doc = yaml.safe_load((settings.content_dir / "redflags.yaml").read_text(encoding="utf-8")) or {}
    return list(doc.get("rules") or [])


def get_rules() -> list[dict[str, Any]]:
    return _override if _override is not None else _loaded()


def set_rules(rules: list[dict[str, Any]] | None) -> None:
    global _override
    _override = rules


def _holds(cond: dict[str, Any], slots: dict[str, Any]) -> bool:
    if slots.get(cond.get("slot")) is None:
        return False
    v = slots[cond["slot"]]
    try:
        if "is" in cond:
            return v == cond["is"]
        if "in" in cond:
            return bool(set(v) & set(cond["in"])) if isinstance(v, list) else v in cond["in"]
        if "gte" in cond:
            return v >= cond["gte"]
        if "lte" in cond:
            return v <= cond["lte"]
    except TypeError:
        return False
    return False


def evaluate(slots: dict[str, Any]) -> list[dict[str, Any]]:
    fired = []
    for rule in get_rules():
        all_ok = all(_holds(c, slots) for c in rule.get("all") or [])
        any_conds = rule.get("any")
        any_ok = any(_holds(c, slots) for c in any_conds) if any_conds else True
        if all_ok and any_ok and (rule.get("all") or any_conds):
            fired.append(rule)
    return fired


def _emit_after_commit(db: DB, payload: dict[str, Any]) -> None:
    """Announce only once the alert is committed, so listeners can always fetch what they're told about."""
    pending: list[dict[str, Any]] = db.info.setdefault("pending_alert_emits", [])
    if not pending:

        def flush(session: DB) -> None:
            for data in session.info.pop("pending_alert_emits", []):
                hub.emit(["alerts", "admin"], "alert.created", data)

        def drop(session: DB) -> None:
            session.info.pop("pending_alert_emits", None)

        event.listen(db, "after_commit", flush, once=True)
        event.listen(db, "after_rollback", drop, once=True)
    pending.append(payload)


def evaluate_and_alert(db: DB, session: Session, slots: dict[str, Any]) -> list[Alert]:
    """Create one Alert per fired rule, at most once per session per rule. Does not commit."""
    created: list[Alert] = []
    for rule in evaluate(slots):
        # Once per session per rule: slots persist across answers, so re-raising after a nurse has
        # confirmed/downgraded would only add noise (deliberately stricter than "open/acknowledged").
        exists = db.exec(select(Alert.id).where(Alert.session_id == session.id, Alert.rule_id == rule["id"])).first()
        if exists:
            continue
        alert = Alert(
            kiosk_id=session.kiosk_id,
            session_id=session.id,
            level=rule["level"],
            rule_id=rule["id"],
            reason_text=rule["reason_text"],
            source=AlertSource.rule.value,
            status=AlertStatus.open.value,
        )
        db.add(alert)
        db.flush()
        audit.record(
            db,
            "system",
            "alert.create",
            "alert",
            alert.id,
            {"session_id": session.id, "rule_id": rule["id"], "level": rule["level"]},
        )
        _emit_after_commit(db, alert_public(alert))
        created.append(alert)
    return created
