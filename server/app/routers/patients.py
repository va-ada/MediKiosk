import json
import re
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app import audit
from app.auth import kiosk_id, kiosk_or_staff
from app.config import settings
from app.db import DbSession
from app.enums import Language, Sex
from app.errors import ApiError
from app.ids import iso_z
from app.models import Patient

router = APIRouter(prefix="/api/patients", tags=["patients"])

KioskId = Annotated[str, Depends(kiosk_id)]
VALID_OTP = "123456"  # mocked ABDM (§4.2)


class RegisterIn(BaseModel):
    """Unknown fields (e.g. anything Aadhaar-like) are silently dropped by Pydantic and never stored."""

    name: str = Field(min_length=1, max_length=120)
    age: int = Field(ge=0, le=120)
    sex: Sex
    language: Language

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("name must not be empty")
        return v


class AbhaVerifyIn(BaseModel):
    abha_number: str
    otp: str


def patient_public(p: Patient) -> dict[str, Any]:
    return {
        "id": p.id,
        "hospital_id": p.hospital_id,
        "name": p.name,
        "age": p.age,
        "sex": p.sex,
        "language": p.language,
        "abha_number": p.abha_number,
        "created_at": iso_z(p.created_at),
    }


@lru_cache
def mock_abha_profiles() -> dict[str, dict[str, Any]]:
    path = settings.content_dir / "mock_abha.json"
    return {p["abha_number"]: p for p in json.loads(path.read_text(encoding="utf-8"))}


def _next_hospital_id(db: Session) -> str:
    last = db.exec(select(Patient.hospital_id).order_by(col(Patient.hospital_id).desc()).limit(1)).first()
    n = int(last.removeprefix("MK-")) + 1 if last else 1
    return f"MK-{n:06d}"


def create_patient(
    db: Session, actor: str, *, name: str, age: int, sex: str, language: str, abha_number: str | None = None
) -> Patient:
    """Insert with the next `MK-NNNNNN`; retries if a concurrent insert took the same number."""
    for _ in range(5):
        patient = Patient(
            hospital_id=_next_hospital_id(db), name=name, age=age, sex=sex, language=language, abha_number=abha_number
        )
        db.add(patient)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            if abha_number:  # a concurrent verify of the same ABHA won the race: reuse that patient
                existing = db.exec(select(Patient).where(Patient.abha_number == abha_number)).first()
                if existing:
                    return existing
            continue
        audit.record(
            db,
            actor,
            "patient.create",
            "patient",
            patient.id,
            {"hospital_id": patient.hospital_id, "via": "abha" if abha_number else "register"},
        )
        db.commit()
        db.refresh(patient)
        return patient
    raise ApiError(409, "conflict", "Could not allocate a hospital id — please retry")


@router.post("/register")
def register(body: RegisterIn, db: DbSession, kiosk: KioskId) -> dict[str, Any]:
    patient = create_patient(
        db, f"kiosk:{kiosk}", name=body.name, age=body.age, sex=body.sex.value, language=body.language.value
    )
    return patient_public(patient)


@router.post("/abha/verify")
def abha_verify(body: AbhaVerifyIn, db: DbSession, kiosk: KioskId) -> dict[str, Any]:
    abha = re.sub(r"[\s-]", "", body.abha_number)
    if not re.fullmatch(r"\d{14}", abha):
        raise ApiError(422, "invalid_abha", "ABHA number must be 14 digits")
    if body.otp.strip() != VALID_OTP:
        raise ApiError(401, "invalid_otp", "Wrong OTP")
    existing = db.exec(select(Patient).where(Patient.abha_number == abha)).first()
    if existing:
        return patient_public(existing)
    profile = mock_abha_profiles().get(abha)
    if profile is None:
        raise ApiError(404, "abha_not_found", "No ABHA record found for this number")
    patient = create_patient(
        db,
        f"kiosk:{kiosk}",
        name=profile["name"],
        age=profile["age"],
        sex=profile["sex"],
        language=profile["language"],
        abha_number=abha,
    )
    return patient_public(patient)


@router.get("/{patient_id}")
def get_patient(patient_id: str, db: DbSession, _actor: Annotated[str, Depends(kiosk_or_staff)]) -> dict[str, Any]:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise ApiError(404, "not_found", "Patient not found")
    return patient_public(patient)
