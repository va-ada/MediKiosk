from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db as app_db
from app import models  # noqa: F401
from app.main import app


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
