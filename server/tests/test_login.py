import importlib.util
from pathlib import Path
from typing import Annotated

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, func, select

from app import audit
from app.auth import check_pin, current_staff, hash_pin, kiosk_id
from app.config import settings
from app.errors import register_error_handlers
from app.models import Setting, Staff

SEED_PATH = Path(__file__).resolve().parents[2] / "scripts" / "seed.py"


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")


def _seed(db: Session) -> dict[str, int]:
    spec = importlib.util.spec_from_file_location("seed", SEED_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.seed(db)


def test_pin_hashing() -> None:
    h = hash_pin("1111")
    assert "$" in h and check_pin("1111", h) and not check_pin("0000", h)
    assert hash_pin("1111") != h  # random salt
    assert not check_pin("1111", "garbage")


def test_seed_is_idempotent(db: Session) -> None:
    assert _seed(db) == {"staff": 6, "settings": 1}
    assert _seed(db) == {"staff": 0, "settings": 0}
    assert db.exec(select(func.count()).select_from(Staff)).one() == 6
    assert db.get(Staff, "D1").room == "Room 1"
    assert db.get(Setting, "island_mode").value is False
    assert audit.verify_chain(db)[0]


def test_login_ok_and_wrong_pin(client: TestClient, db: Session) -> None:
    _seed(db)
    res = client.post("/api/staff/login", json={"staff_id": "D1", "pin": "1111"})
    assert res.status_code == 200
    body = res.json()
    assert body["staff"] == {
        "id": "D1",
        "name": "Dr. Mehta",
        "role": "doctor",
        "department": "ayurveda",
        "room": "Room 1",
    }
    claims = jwt.decode(body["token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["sub"] == "D1" and claims["role"] == "doctor"

    for bad in ({"staff_id": "D1", "pin": "0000"}, {"staff_id": "ZZ", "pin": "1111"}):
        res = client.post("/api/staff/login", json=bad)
        assert res.status_code == 401
        assert res.json() == {"error": {"code": "invalid_pin", "message": "Wrong staff ID or PIN"}}


def test_dependencies(client: TestClient, db: Session) -> None:
    _seed(db)
    tok = {
        sid: client.post("/api/staff/login", json={"staff_id": sid, "pin": pin}).json()["token"]
        for sid, pin in (("D1", "1111"), ("N1", "3333"))
    }

    probe = FastAPI()
    register_error_handlers(probe)

    @probe.get("/doc")
    def doc_only(staff: Annotated[Staff, Depends(current_staff(["doctor"]))]) -> dict:
        return {"id": staff.id}

    @probe.get("/kiosk")
    def kiosk(kid: Annotated[str, Depends(kiosk_id)]) -> dict:
        return {"kiosk": kid}

    probe.dependency_overrides = client.app.dependency_overrides  # same test DB
    c = TestClient(probe)
    assert c.get("/doc").json()["error"]["code"] == "unauthorized"
    assert c.get("/doc", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/doc", headers={"Authorization": f"Bearer {tok['N1']}"}).json()["error"]["code"] == "forbidden"
    assert c.get("/doc", headers={"Authorization": f"Bearer {tok['D1']}"}).json() == {"id": "D1"}
    assert c.get("/kiosk").json()["error"]["code"] == "missing_kiosk_id"
    assert c.get("/kiosk", headers={"X-Kiosk-Id": "KIOSK-01"}).json() == {"kiosk": "KIOSK-01"}
