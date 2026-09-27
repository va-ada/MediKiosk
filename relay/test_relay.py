import uuid

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client() -> TestClient:
    main.alarms.clear()
    main.clients.clear()
    return TestClient(main.app)


def alarm(reason: str = "chest_pain") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "kiosk_id": "KIOSK-01",
        "reason_code": reason,
        "created_at": "2026-10-12T05:02:11Z",
    }


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_duplicate_id_is_flagged_and_stored_once(client: TestClient) -> None:
    a = alarm()
    assert client.post("/alarm", json=a).json() == {"ok": True, "duplicate": False}
    assert client.post("/alarm", json=a).json() == {"ok": True, "duplicate": True}
    assert client.get("/alarms").json() == [a]


def test_ws_client_receives_exactly_one_message_per_alarm(client: TestClient) -> None:
    a, b = alarm(), alarm("seizure")
    with client.websocket_connect("/ws") as ws:
        client.post("/alarm", json=a)
        client.post("/alarm", json=a)  # duplicate: must not be broadcast
        client.post("/alarm", json=b)
        assert ws.receive_json() == {"type": "alarm", "data": a}
        # The next message is b, so the duplicate of a was never sent.
        assert ws.receive_json() == {"type": "alarm", "data": b}


def test_alarms_newest_first_capped_at_50(client: TestClient) -> None:
    sent = [alarm() for _ in range(60)]
    for a in sent:
        client.post("/alarm", json=a)
    got = client.get("/alarms").json()
    assert len(got) == 50
    assert got[0]["id"] == sent[-1]["id"]
    assert got[-1]["id"] == sent[10]["id"]


def test_memory_capped_at_200(client: TestClient) -> None:
    for _ in range(250):
        client.post("/alarm", json=alarm())
    assert len(main.alarms) == main.MAX_ALARMS


def test_bad_reason_code_uses_error_shape(client: TestClient) -> None:
    r = client.post("/alarm", json={**alarm(), "reason_code": "hiccups"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_cors_allows_any_origin(client: TestClient) -> None:
    r = client.get("/alarms", headers={"Origin": "http://192.168.1.5:5173"})
    assert r.headers["access-control-allow-origin"] == "*"
