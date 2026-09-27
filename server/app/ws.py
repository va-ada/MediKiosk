"""WebSocket hub (CONTRACTS.md §5): `ws://<host>:8000/ws?channel=queue|alerts|display|admin`.

Every message is `{"type", "data", "ts"}`. `emit()` may be called from sync route handlers, which
FastAPI runs in a threadpool with no event loop: the hub remembers the server's loop when the first
socket connects and schedules sends onto it. With no loop (or no sockets) `emit()` is a silent no-op.
"""

import asyncio
from collections.abc import Iterable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ids import iso_z, utcnow

CHANNELS = ("queue", "alerts", "display", "admin")


class Hub:
    def __init__(self) -> None:
        self.sockets: dict[str, set[WebSocket]] = {c: set() for c in CHANNELS}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, channel: str, ws: WebSocket) -> None:
        self.loop = asyncio.get_running_loop()
        self.sockets[channel].add(ws)

    def disconnect(self, channel: str, ws: WebSocket) -> None:
        self.sockets[channel].discard(ws)

    async def publish(self, channel: str, type: str, data: Any) -> None:
        message = {"type": type, "data": data, "ts": iso_z(utcnow())}
        for ws in list(self.sockets.get(channel, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001  dead socket: drop it, keep going
                self.disconnect(channel, ws)

    async def publish_many(self, channels: Iterable[str], type: str, data: Any) -> None:
        for channel in channels:
            await self.publish(channel, type, data)

    def emit(self, channels: Iterable[str] | str, type: str, data: Any) -> None:
        """Fire-and-forget publish, callable from sync or async code."""
        chans = [channels] if isinstance(channels, str) else list(channels)
        coro = self.publish_many(chans, type, data)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            running.create_task(coro)
        elif self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            coro.close()


hub = Hub()
router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, channel: str = "") -> None:
    await websocket.accept()
    if channel not in CHANNELS:
        await websocket.close(code=1008)
        return
    await hub.connect(channel, websocket)
    try:
        while True:
            await websocket.receive_text()  # clients don't send; this just waits for disconnect
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(channel, websocket)
