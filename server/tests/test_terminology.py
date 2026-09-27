import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.auth import create_jwt, hash_pin
from app.config import settings
from app.models import Staff
from app.services import terminology

DATA = [
    {"system": "NAMASTE", "code": "SAMPLE-NAM-001", "display": "Sandhigata Vata (knee osteoarthritis)", "sample": True},
    {"system": "NAMASTE", "code": "SAMPLE-NAM-002", "display": "Amavata (inflammatory joint disorder)", "sample": True},
    {"system": "ICD10", "code": "SAMPLE-ICD10-001", "display": "Osteoarthritis of knee", "sample": True},
    {"system": "ICD10", "code": "SAMPLE-ICD10-004", "display": "Type 2 diabetes mellitus", "sample": True},
]


def test_search_ranks_and_filters() -> None:
    assert terminology.search("sandhigata", data=DATA)[0]["code"] == "SAMPLE-NAM-001"
    assert terminology.search("knee", system="ICD10", data=DATA)[0]["code"] == "SAMPLE-ICD10-001"
    assert all(r["system"] == "ICD10" for r in terminology.search("knee", system="ICD10", data=DATA))
    assert terminology.search("SAMPLE-NAM-002", data=DATA)[0]["display"].startswith("Amavata")
    assert terminology.search("   ", data=DATA) == []
    assert terminology.search("zzzzqqq", data=DATA) == []
    assert terminology.search("sandhi")[0]["code"] == "SAMPLE-NAM-001"  # prefix beats fuzzy


def test_real_file_limits() -> None:
    res = terminology.search("sample")
    assert 0 < len(res) <= 10
    assert all(set(r) == {"system", "code", "display", "sample"} and r["sample"] is True for r in res)


def test_route_doctor_only(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-test-secret-test-secret!")
    doc = Staff(id="D1", name="Dr. Mehta", role="doctor", department="ayurveda", pin_hash=hash_pin("1"))
    nurse = Staff(id="N1", name="Nurse", role="nurse", pin_hash=hash_pin("1"))
    db.add_all([doc, nurse])
    db.commit()
    h = {"Authorization": f"Bearer {create_jwt(doc)}"}
    res = client.get("/api/terminology/search?q=sandhigata&system=NAMASTE", headers=h).json()
    assert res[0]["code"] == "SAMPLE-NAM-001" and res[0]["sample"] is True
    assert client.get("/api/terminology/search?q=x&system=BAD", headers=h).status_code == 422
    assert (
        client.get("/api/terminology/search?q=x", headers={"Authorization": f"Bearer {create_jwt(nurse)}"}).status_code
        == 403
    )
