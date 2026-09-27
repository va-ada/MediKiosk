from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlmodel import select

from app import audit
from app.auth import current_staff
from app.db import DbSession
from app.enums import Section, SourceType, Trust
from app.errors import ApiError
from app.ids import iso_z, utcnow
from app.models import Diagnosis, Fact, SectionApproval, SectionView, Staff
from app.routers.sessions import get_session_or_404
from app.routers.summary import rebuild

router = APIRouter(tags=["review"])

Doctor = Annotated[Staff, Depends(current_staff(["doctor"]))]


class VerifyIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    value: Any = None
    text_en: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _edit_needs_change(self) -> "VerifyIn":
        if self.action == "edit" and self.value is None and not (self.text_en or "").strip():
            raise ValueError("edit needs value or text_en")
        return self


class ExamFinding(BaseModel):
    value: str = Field(max_length=40)
    note: str | None = Field(default=None, max_length=300)


class Pramana(BaseModel):
    height_cm: float = Field(gt=30, lt=260)
    weight_kg: float = Field(gt=1, lt=350)


class AyushExamIn(BaseModel):
    nadi: ExamFinding | str | None = None
    jihva: ExamFinding | str | None = None
    pramana: Pramana | None = None
    sara: ExamFinding | str | None = None
    samhanana: ExamFinding | str | None = None
    vikriti: ExamFinding | str | None = None
    notes: str | None = Field(default=None, max_length=1000)


class CodeIn(BaseModel):
    system: Literal["NAMASTE", "ICD11_TM2", "ICD10"]
    code: str = Field(min_length=1, max_length=40)
    display: str = Field(min_length=1, max_length=200)


class DiagnosisIn(BaseModel):
    codes: list[CodeIn] = Field(max_length=20)
    text: str | None = Field(default=None, max_length=1000)


def fact_public(f: Fact) -> dict[str, Any]:
    return {
        "id": f.id,
        "session_id": f.session_id,
        "patient_id": f.patient_id,
        "section": f.section,
        "key": f.key,
        "value": f.value,
        "text_en": f.text_en,
        "patient_words": f.patient_words,
        "trust": f.trust,
        "source_type": f.source_type,
        "source_id": f.source_id,
        "bbox": f.bbox,
        "created_at": iso_z(f.created_at),
        "verified_by": f.verified_by,
        "verified_at": iso_z(f.verified_at),
    }


def _section(section: str) -> str:
    if section not in {s.value for s in Section}:
        raise ApiError(404, "not_found", f"Unknown section {section}")
    return section


@router.post("/api/sessions/{session_id}/sections/{section}/open")
def open_section(session_id: str, section: str, db: DbSession, doctor: Doctor) -> dict[str, bool]:
    s = get_session_or_404(db, session_id)
    sec = _section(section)
    view = SectionView(session_id=s.id, staff_id=doctor.id, section=sec)
    db.add(view)
    db.flush()
    audit.record(db, f"staff:{doctor.id}", "section.open", "session", s.id, {"section": sec})
    rebuild(db, s, f"staff:{doctor.id}")
    return {"ok": True}


@router.post("/api/sessions/{session_id}/sections/{section}/approve")
def approve_section(session_id: str, section: str, db: DbSession, doctor: Doctor) -> dict[str, bool]:
    s = get_session_or_404(db, session_id)
    sec = _section(section)
    opened = db.exec(
        select(SectionView.id).where(
            SectionView.session_id == s.id, SectionView.section == sec, SectionView.staff_id == doctor.id
        )
    ).first()
    if not opened:
        raise ApiError(409, "section_not_opened", "Open the section before approving it")
    now = utcnow()
    facts = db.exec(
        select(Fact).where(Fact.session_id == s.id, Fact.section == sec, Fact.trust != Trust.rejected)
    ).all()
    for f in facts:
        f.trust, f.verified_by, f.verified_at = Trust.doctor_verified.value, doctor.id, now
        db.add(f)
    db.add(SectionApproval(session_id=s.id, section=sec, staff_id=doctor.id, approved_at=now))
    audit.record(
        db,
        f"staff:{doctor.id}",
        "section.approve",
        "session",
        s.id,
        {"section": sec, "fact_ids": [f.id for f in facts]},
    )
    rebuild(db, s, f"staff:{doctor.id}")
    return {"ok": True}


@router.post("/api/facts/{fact_id}/verify")
def verify_fact(fact_id: str, body: VerifyIn, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    f = db.get(Fact, fact_id)
    if f is None:
        raise ApiError(404, "not_found", "Fact not found")
    before = {"trust": f.trust, "value": f.value, "text_en": f.text_en}
    if body.action == "reject":
        f.trust = Trust.rejected.value
    else:
        if body.action == "edit":
            if body.value is not None:
                f.value = body.value
            if (body.text_en or "").strip():
                f.text_en = body.text_en.strip()
        f.trust = Trust.doctor_verified.value
    f.verified_by, f.verified_at = doctor.id, utcnow()
    db.add(f)
    audit.record(
        db,
        f"staff:{doctor.id}",
        "fact.verify",
        "fact",
        f.id,
        {"action": body.action, "before": before, "after": {"trust": f.trust, "value": f.value, "text_en": f.text_en}},
    )
    rebuild(db, get_session_or_404(db, f.session_id), f"staff:{doctor.id}")
    db.refresh(f)
    return fact_public(f)


def _finding_text(label: str, finding: ExamFinding | str) -> tuple[dict[str, Any], str]:
    if isinstance(finding, str):
        finding = ExamFinding(value=finding)
    note = (finding.note or "").strip()
    return {"value": finding.value, "note": note or None}, f"{label}: {finding.value}" + (f" — {note}" if note else "")


@router.post("/api/sessions/{session_id}/ayush-exam")
def ayush_exam(session_id: str, body: AyushExamIn, db: DbSession, doctor: Doctor) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    now = utcnow()
    entries: list[tuple[str, dict[str, Any], str]] = []
    for key, label in (
        ("nadi", "Nadi"),
        ("jihva", "Jihva"),
        ("sara", "Sara"),
        ("samhanana", "Samhanana"),
        ("vikriti", "Vikriti"),
    ):
        finding = getattr(body, key)
        if finding is not None:
            value, text = _finding_text(label, finding)
            entries.append((f"exam_{key}", value, text))
    if body.pramana:
        h, w = body.pramana.height_cm, body.pramana.weight_kg
        bmi = round(w / (h / 100) ** 2, 1)
        entries.append(
            (
                "exam_pramana",
                {"height_cm": h, "weight_kg": w, "bmi": bmi},
                f"Pramana: height {h:g} cm, weight {w:g} kg, BMI {bmi}",
            )
        )
    if (body.notes or "").strip():
        entries.append(("exam_notes", {"value": body.notes.strip()}, f"Examination notes: {body.notes.strip()}"))
    if not entries:
        raise ApiError(422, "validation_error", "Nothing to record")

    created = []
    for key, value, text in entries:
        for old in db.exec(
            select(Fact).where(Fact.session_id == s.id, Fact.key == key, Fact.source_type == SourceType.doctor)
        ).all():
            db.delete(old)  # re-saving the exam replaces the previous finding (audit keeps the history)
        f = Fact(
            session_id=s.id,
            patient_id=s.patient_id,
            section=Section.ayush.value,
            key=key,
            value=value,
            text_en=text,
            trust=Trust.doctor_verified.value,
            source_type=SourceType.doctor.value,
            verified_by=doctor.id,
            verified_at=now,
        )
        db.add(f)
        created.append(f)
    db.flush()
    audit.record(
        db,
        f"staff:{doctor.id}",
        "ayush_exam.save",
        "session",
        s.id,
        {"facts": [{"id": f.id, "key": f.key, "text_en": f.text_en} for f in created]},
    )
    rebuild(db, s, f"staff:{doctor.id}")
    for f in created:
        db.refresh(f)
    return {"facts": [fact_public(f) for f in created]}


@router.post("/api/sessions/{session_id}/diagnosis")
def diagnosis(session_id: str, body: DiagnosisIn, db: DbSession, doctor: Doctor) -> dict[str, bool]:
    s = get_session_or_404(db, session_id)
    if not body.codes and not (body.text or "").strip():
        raise ApiError(422, "validation_error", "Add at least one code or a diagnosis text")
    d = Diagnosis(
        session_id=s.id,
        staff_id=doctor.id,
        codes=[c.model_dump() for c in body.codes],
        text=(body.text or "").strip() or None,
    )
    db.add(d)
    db.flush()
    audit.record(db, f"staff:{doctor.id}", "diagnosis.create", "diagnosis", d.id, {"codes": d.codes, "text": d.text})
    db.commit()
    return {"ok": True}
