import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


def today_ist() -> date:
    """`token.day` is the local hospital date (Asia/Kolkata), not the UTC date."""
    return datetime.now(IST).date()


def iso_z(dt: datetime | None) -> str | None:
    """ISO 8601 UTC with a trailing `Z` (§1). Naive datetimes (SQLite) are treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
