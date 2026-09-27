import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main


def sample_bundle(name: str = "Kamla Devi") -> dict:
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1", "name": [{"text": name}]}},
            {"resource": {"resourceType": "Condition", "id": "c1"}},
            {"resource": {"resourceType": "Observation", "id": "o1"}},
            {"resource": {"resourceType": "Observation", "id": "o2"}},
        ],
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "his")
    with TestClient(main.app) as c:
        yield c


def post(client: TestClient, bundle: dict, key: str | None = "s1:v1"):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post("/fhir", json=bundle, headers=headers)


def test_missing_idempotency_key_is_400(client: TestClient) -> None:
    r = post(client, sample_bundle(), key=None)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "missing_idempotency_key"
    assert client.get("/bundles").json() == []


def test_receive_stores_in_memory_and_on_disk(client: TestClient) -> None:
    r = post(client, sample_bundle())
    assert r.status_code == 200
    body = r.json()
    assert body["received"] is True and body["duplicate"] is False
    listed = client.get("/bundles").json()
    assert len(listed) == 1 and listed[0]["id"] == body["id"] and listed[0]["bundle"] == sample_bundle()
    on_disk = json.loads((main.DATA_DIR / f"{body['id']}.json").read_text())
    assert on_disk["idempotency_key"] == "s1:v1"


def test_duplicate_key_not_stored_twice(client: TestClient) -> None:
    first = post(client, sample_bundle()).json()
    second = post(client, sample_bundle()).json()
    assert second == {"received": True, "id": first["id"], "duplicate": True}
    assert len(client.get("/bundles").json()) == 1
    assert len(list(main.DATA_DIR.glob("*.json"))) == 1
    third = post(client, sample_bundle(), key="s1:v2").json()
    assert third["duplicate"] is False and len(client.get("/bundles").json()) == 2


def test_not_a_bundle_is_400(client: TestClient) -> None:
    r = post(client, {"resourceType": "Patient"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_bundle"


def test_bundles_survive_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "DATA_DIR", tmp_path / "his")
    with TestClient(main.app) as c:
        first = post(c, sample_bundle()).json()
    main.bundles.clear()
    with TestClient(main.app) as c:
        assert post(c, sample_bundle()).json()["duplicate"] is True
        assert [b["id"] for b in c.get("/bundles").json()] == [first["id"]]


def test_html_page_lists_bundle(client: TestClient) -> None:
    post(client, sample_bundle())
    page = client.get("/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert "Kamla Devi" in page.text
    assert "Observation × 2" in page.text
    assert "Condition × 1" in page.text


def test_html_escapes_bundle_content(client: TestClient) -> None:
    post(client, sample_bundle(name="<script>alert(1)</script>"), key='<img src=x onerror="alert(2)">')
    page = client.get("/").text
    assert "<script>alert(1)" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<img src=x" not in page
