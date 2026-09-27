"""Alarm relay (CONTRACTS §7) — tiny standalone service, independent of the API server.

Kiosks POST emergency alarms here directly so the triage station still hears them if the
API server is down. No database: alarms live in memory (last 200), deduplicated by `id`.
"""

from collections import deque
from typing import Literal

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

MAX_ALARMS = 200
LIST_LIMIT = 50

ReasonCode = Literal[
    "chest_pain",
    "breathing",
    "bleeding",
    "unconscious",
    "seizure",
    "stroke_signs",
    "severe_pain",
    "pregnancy",
    "other",
]


class Alarm(BaseModel):
    id: str
    kiosk_id: str
    reason_code: ReasonCode
    created_at: str


class AlarmAck(BaseModel):
    ok: bool
    duplicate: bool


app = FastAPI(title="MediKiosk alarm relay", version="0.1.0")
# The triage web page (:5173) reads /alarms straight from the browser.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

alarms: deque[dict] = deque(maxlen=MAX_ALARMS)
clients: set[WebSocket] = set()


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    message = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": message}})


async def broadcast(message: dict) -> None:
    for ws in list(clients):
        try:
            await ws.send_json(message)
        except (WebSocketDisconnect, RuntimeError, OSError):  # client went away mid-send
            clients.discard(ws)


@app.post("/alarm")
async def post_alarm(alarm: Alarm) -> AlarmAck:
    if any(a["id"] == alarm.id for a in alarms):
        return AlarmAck(ok=True, duplicate=True)
    data = alarm.model_dump()
    alarms.append(data)
    await broadcast({"type": "alarm", "data": data})
    return AlarmAck(ok=True, duplicate=False)


@app.get("/alarms")
def list_alarms() -> list[Alarm]:
    """Last 50 alarms, newest first."""
    return [Alarm(**a) for a in reversed(list(alarms)[-LIST_LIMIT:])]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()  # clients don't send anything meaningful; keep the socket open
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
