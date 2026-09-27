"""Queue selector and preview (CONTRACTS.md §10.2)."""

from datetime import timedelta

from sqlmodel import Session as DB
from sqlmodel import col, select

from app.config import settings
from app.enums import Lane, TokenStatus
from app.ids import as_utc, today_ist, utcnow
from app.models import Staff, Token

LANE_ORDER = {Lane.emergency.value: 0, Lane.priority.value: 1, Lane.normal.value: 2}
ACTIVE = (TokenStatus.called.value, TokenStatus.in_.value)


def _today(db: DB, department: str | None, statuses: tuple[str, ...]) -> list[Token]:
    q = select(Token).where(Token.day == today_ist(), col(Token.status).in_(statuses))
    if department:
        q = q.where(Token.department == department)
    return list(db.exec(q.order_by(col(Token.arrival_seq))))


def is_aged(token: Token) -> bool:
    return (
        token.lane == Lane.normal
        and token.status == TokenStatus.waiting
        and utcnow() - as_utc(token.created_at) >= timedelta(minutes=settings.wait_limit_min)
    )


def preview(db: DB, department: str | None) -> list[Token]:
    """Waiting tokens: emergency, priority, normal — each by arrival_seq."""
    waiting = _today(db, department, (TokenStatus.waiting.value,))
    return sorted(waiting, key=lambda t: (LANE_ORDER.get(t.lane, 9), t.arrival_seq))


def board(db: DB, department: str | None) -> list[Token]:
    """Doctor board: the waiting preview, then today's called/in tokens (so In / No-show stay reachable)."""
    return preview(db, department) + _today(db, department, ACTIVE)


def select_next(db: DB, department: str, doctor_id: str) -> Token | None:
    candidates = _today(db, department, (TokenStatus.waiting.value,))  # already ordered by arrival_seq
    for t in candidates:
        if t.lane == Lane.emergency:
            return t
    for t in candidates:
        if is_aged(t):
            return t
    for t in candidates:
        if t.lane == Lane.priority and t.preferred_doctor_id in (None, doctor_id):
            return t
    for t in candidates:
        if t.lane == Lane.normal:
            return t
    return None


def mark_called(db: DB, token: Token, doctor: Staff) -> Token:
    """call → `called`, called_count + 1. The calling doctor is recorded so the display board can show room."""
    token.status = TokenStatus.called.value
    token.called_count += 1
    token.called_at = utcnow()
    token.doctor_id = doctor.id
    db.add(token)
    db.flush()
    return token


def now_serving(db: DB, department: str | None, limit: int = 3) -> list[Token]:
    tokens = _today(db, department, ACTIVE)
    return sorted(tokens, key=lambda t: as_utc(t.called_at) if t.called_at else as_utc(t.created_at), reverse=True)[
        :limit
    ]
