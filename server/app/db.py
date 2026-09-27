from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)


def init_db() -> None:
    """Create every §3 table (idempotent). Reads the module-level `engine` so tests can swap it."""
    from app import models  # noqa: F401  (registers the tables on SQLModel.metadata)

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one DB session per request."""
    with Session(engine) as db:
        yield db


DbSession = Annotated[Session, Depends(get_session)]
