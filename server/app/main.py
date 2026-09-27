import importlib
import pkgutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db, routers
from app.errors import register_error_handlers

VERSION = "0.1.0"


def include_routers(app: FastAPI) -> None:
    """Auto-include every `app/routers/<module>.py` that exposes `router`."""
    for info in sorted(pkgutil.iter_modules(routers.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{routers.__name__}.{info.name}")
        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="MediKiosk API", version=VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"]
    )
    register_error_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    include_routers(app)
    return app


app = create_app()
