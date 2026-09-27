import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.ws import Hub, hub, router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)

    @app.post("/publish")
    async def publish() -> dict:
        await hub.publish("queue", "token.created", {"display": "A-001"})
        return {"ok": True}

    @app.post("/emit-sync")
    def emit_sync() -> dict:  # runs in a threadpool: exercises the thread-safe path
        hub.emit(["queue", "display"], "token.updated", {"display": "A-002"})
        return {"ok": True}

    return app


def test_publish_reaches_subscriber() -> None:
    client = TestClient(_app())
    with client.websocket_connect("/ws?channel=queue") as ws:
        client.post("/publish")
        msg = ws.receive_json()
    assert msg["type"] == "token.created"
    assert msg["data"] == {"display": "A-001"}
    assert msg["ts"].endswith("Z")


def test_emit_from_sync_route() -> None:
    client = TestClient(_app())
    with client.websocket_connect("/ws?channel=display") as ws:
        client.post("/emit-sync")
        assert ws.receive_json()["data"] == {"display": "A-002"}


def test_unknown_channel_closed_1008() -> None:
    client = TestClient(_app())
    with client.websocket_connect("/ws?channel=nope") as ws, pytest.raises(WebSocketDisconnect) as exc:
        ws.receive_json()
    assert exc.value.code == 1008


def test_emit_without_loop_is_noop() -> None:
    Hub().emit("queue", "x", {})  # must not raise
