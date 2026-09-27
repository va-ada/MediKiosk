from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db as app_db
from app import models  # noqa: F401
from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _no_background_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outbox/escalation loops would share the in-memory DB connection with the test; test them directly."""
    monkeypatch.setattr(settings, "run_workers", False)


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch):
    """Fresh in-memory SQLite per test, swapped in for the Postgres engine."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    monkeypatch.setattr(app_db, "engine", eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine) -> Iterator[TestClient]:
    def _get_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[app_db.get_session] = _get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def kiosk_headers() -> dict[str, str]:
    return {"X-Kiosk-Id": "KIOSK-01"}


@pytest.fixture
def staff_headers(db: Session, monkeypatch: pytest.MonkeyPatch):
    """`staff_headers("doctor")` → Bearer headers for a staff member with that role (created on first use)."""
    from app.auth import create_jwt, hash_pin
    from app.models import Staff

    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")

    def make(role: str, staff_id: str | None = None) -> dict[str, str]:
        sid = staff_id or f"T-{role.upper()}"
        staff = db.get(Staff, sid)
        if staff is None:
            staff = Staff(
                id=sid,
                name=f"Test {role}",
                role=role,
                department="ayurveda" if role == "doctor" else None,
                room="Room 9" if role == "doctor" else None,
                pin_hash=hash_pin("0000"),
            )
            db.add(staff)
            db.commit()
        return {"Authorization": f"Bearer {create_jwt(staff)}"}

    return make
