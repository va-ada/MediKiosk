"""Seed demo staff and settings (idempotent).

Run from `server/`:  uv run python ../scripts/seed.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from sqlmodel import Session

from app import audit, db
from app.auth import hash_pin
from app.models import Setting, Staff

# (id, name, role, department, room, pin)
STAFF: list[tuple[str, str, str, str | None, str | None, str]] = [
    ("D1", "Dr. Mehta", "doctor", "ayurveda", "Room 1", "1111"),
    ("D2", "Dr. Rao", "doctor", "general", "Room 2", "2222"),
    ("N1", "Nurse Asha", "nurse", None, None, "3333"),
    ("K1", "Desk Ravi", "desk", None, None, "4444"),
    ("A1", "Admin Priya", "admin", None, None, "5555"),
    ("A2", "Admin Sunil", "admin", None, None, "6666"),
]
SETTINGS: dict[str, object] = {"island_mode": False}


def seed(session: Session) -> dict[str, int]:
    """Create missing staff and settings; existing rows (and their PINs) are left alone."""
    created = {"staff": 0, "settings": 0}
    for sid, name, role, dept, room, pin in STAFF:
        if session.get(Staff, sid) is None:
            session.add(Staff(id=sid, name=name, role=role, department=dept, room=room, pin_hash=hash_pin(pin)))
            audit.record(session, "system", "staff.create", "staff", sid, {"name": name, "role": role})
            created["staff"] += 1
    for key, value in SETTINGS.items():
        if session.get(Setting, key) is None:
            session.add(Setting(key=key, value=value))
            audit.record(session, "system", "setting.create", "setting", key, {"value": value})
            created["settings"] += 1
    session.commit()
    return created


def main() -> None:
    db.init_db()
    with Session(db.engine) as session:
        created = seed(session)
    print(
        f"Seeded: {created['staff']} new staff, {created['settings']} new settings "
        f"({len(STAFF)} staff and {len(SETTINGS)} settings expected in total)"
    )


if __name__ == "__main__":
    main()
