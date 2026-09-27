"""Token numbering (CONTRACTS.md §10.1)."""

from datetime import date

from sqlalchemy import func, text
from sqlmodel import Session as DB
from sqlmodel import select

from app.config import settings
from app.enums import Lane, TokenStatus
from app.ids import today_ist
from app.models import Session, Token


def _lock_numbering(db: DB) -> None:
    """Serialise number/arrival_seq allocation across connections (Postgres only)."""
    if db.get_bind().dialect.name == "postgresql":
        db.exec(text("SELECT pg_advisory_xact_lock(74657)"))  # type: ignore[call-overload]


def issue_token(
    db: DB,
    session: Session,
    department: str,
    lane: str = Lane.normal.value,
    arrival_seq: int | None = None,
    day: date | None = None,
    preferred_doctor_id: str | None = None,
) -> Token:
    """display = f"{prefix}-{number:03d}"; number = 1 + max for (prefix, day); arrival_seq = 1 + global max."""
    _lock_numbering(db)
    prefix = settings.server_prefix
    day = day or today_ist()
    last_number = db.exec(select(func.max(Token.number)).where(Token.prefix == prefix, Token.day == day)).one()
    number = (last_number or 0) + 1
    if arrival_seq is None:
        arrival_seq = (db.exec(select(func.max(Token.arrival_seq))).one() or 0) + 1
    token = Token(
        display=f"{prefix}-{number:03d}",
        prefix=prefix,
        number=number,
        day=day,
        patient_id=session.patient_id,
        session_id=session.id,
        department=department,
        lane=lane,
        status=TokenStatus.waiting.value,
        arrival_seq=arrival_seq,
        preferred_doctor_id=preferred_doctor_id,
    )
    db.add(token)
    db.flush()
    return token


def latest_token(db: DB, session_id: str) -> Token | None:
    return db.exec(
        select(Token).where(Token.session_id == session_id).order_by(Token.created_at.desc())  # type: ignore[attr-defined]
    ).first()
