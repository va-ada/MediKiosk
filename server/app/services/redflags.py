"""Red-flag rules engine — stub until S8."""

from typing import Any

from sqlmodel import Session as DB

from app.models import Alert, Session


def evaluate_and_alert(db: DB, session: Session, slots: dict[str, Any]) -> list[Alert]:
    # TODO(S8): evaluate content/redflags.yaml rules and create alerts.
    return []
