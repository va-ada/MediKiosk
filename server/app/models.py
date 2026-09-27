"""Every table from CONTRACTS.md §3.

Enum-typed columns are stored as plain strings (not native Postgres ENUM types) so tables can be
dropped and recreated freely. JSON columns are not mutation-tracked: to change `fact.value` (or any
JSON field), assign a new object — `fact.value = {**fact.value, "patient_unsure": True}`.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index
from sqlmodel import Field, SQLModel

from app.ids import new_id, utcnow


def _ts(nullable: bool = True, **kw: Any) -> Any:
    return Field(default=None, sa_type=DateTime(timezone=True), nullable=nullable, **kw)


def _created() -> Any:
    return Field(default_factory=utcnow, sa_type=DateTime(timezone=True), nullable=False)


def _json(nullable: bool = True, default: Any = None) -> Any:
    if default is not None:
        return Field(default_factory=default, sa_column=Column(JSON, nullable=nullable))
    return Field(default=None, sa_column=Column(JSON, nullable=nullable))


class Staff(SQLModel, table=True):
    __tablename__ = "staff"
    id: str = Field(primary_key=True)  # seeded ids: D1, D2, N1, K1, A1, A2
    name: str
    role: str  # Role
    department: str | None = None  # Department
    room: str | None = None
    pin_hash: str
    active: bool = True


class Patient(SQLModel, table=True):
    __tablename__ = "patient"
    id: str = Field(default_factory=new_id, primary_key=True)
    hospital_id: str = Field(unique=True, index=True)  # MK-000001
    name: str
    age: int
    sex: str  # Sex
    language: str  # Language
    abha_number: str | None = Field(default=None, unique=True, index=True)  # 14 digits; never Aadhaar
    created_at: datetime = _created()


class Session(SQLModel, table=True):
    __tablename__ = "session"
    id: str = Field(default_factory=new_id, primary_key=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    kiosk_id: str
    informant: str  # Informant
    informant_relation: str | None = None
    status: str  # SessionStatus
    legal_basis: str  # LegalBasis
    complaint_code: str | None = None  # ComplaintCode
    pathway: str | None = None
    department: str | None = None  # Department
    created_at: datetime = _created()
    submitted_at: datetime | None = _ts()
    opened_by_doctor_at: datetime | None = _ts()
    closed_at: datetime | None = _ts()


class Consent(SQLModel, table=True):
    __tablename__ = "consent"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    capture: bool
    scan: bool
    share_hospital: bool
    link_abha: bool
    check_passed: bool
    created_at: datetime = _created()
    revoked_at: datetime | None = _ts()


class Token(SQLModel, table=True):
    __tablename__ = "token"
    __table_args__ = (Index("ix_token_day_department_status", "day", "department", "status"),)
    id: str = Field(default_factory=new_id, primary_key=True)
    display: str  # A-017
    prefix: str
    number: int
    day: date  # local date, Asia/Kolkata
    patient_id: str = Field(foreign_key="patient.id")
    session_id: str = Field(foreign_key="session.id", index=True)
    department: str  # Department
    lane: str  # Lane
    status: str  # TokenStatus
    arrival_seq: int
    called_count: int = 0
    doctor_id: str | None = Field(default=None, foreign_key="staff.id")
    preferred_doctor_id: str | None = Field(default=None, foreign_key="staff.id")
    created_at: datetime = _created()
    called_at: datetime | None = _ts()
    in_at: datetime | None = _ts()
    closed_at: datetime | None = _ts()
    outcome: str | None = None  # Outcome
    outcome_note: str | None = None
    followup_date: date | None = None


class Answer(SQLModel, table=True):
    __tablename__ = "answer"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    question_id: str
    source: str  # AnswerSource
    raw_text: str | None = None
    confidence: float | None = None
    slots: dict[str, Any] = _json(nullable=False, default=dict)
    status: str  # AnswerStatus
    created_at: datetime = _created()


class Fact(SQLModel, table=True):
    __tablename__ = "fact"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    patient_id: str = Field(foreign_key="patient.id", index=True)
    section: str  # Section
    key: str
    value: Any = _json(nullable=True)
    text_en: str
    patient_words: str | None = None
    trust: str  # Trust
    source_type: str  # SourceType
    source_id: str | None = None
    bbox: list[float] | None = _json(nullable=True)
    created_at: datetime = _created()
    verified_by: str | None = Field(default=None, foreign_key="staff.id")
    verified_at: datetime | None = _ts()


class Document(SQLModel, table=True):
    __tablename__ = "document"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    patient_id: str = Field(foreign_key="patient.id")
    file_path: str
    page_no: int = 1
    doc_type: str = "unknown"  # DocType
    doc_date: date | None = None
    ocr_json: dict[str, Any] | None = _json(nullable=True)
    status: str = "pending"  # DocStatus
    pinned: bool = False
    created_at: datetime = _created()


class Readback(SQLModel, table=True):
    __tablename__ = "readback"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    fact_id: str = Field(foreign_key="fact.id")
    response: str | None = None  # ReadbackResponse
    created_at: datetime = _created()


class Alert(SQLModel, table=True):
    __tablename__ = "alert"
    id: str = Field(default_factory=new_id, primary_key=True)  # client may supply
    kiosk_id: str
    session_id: str | None = Field(default=None, foreign_key="session.id", index=True)
    level: str  # AlertLevel
    reason_code: str | None = None  # ReasonCode
    rule_id: str | None = None
    reason_text: str
    source: str  # AlertSource
    status: str = "open"  # AlertStatus
    escalated: bool = False
    created_at: datetime = _created()
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = _ts()
    resolved_by: str | None = None
    resolved_at: datetime | None = _ts()


class Summary(SQLModel, table=True):
    __tablename__ = "summary"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    version: int
    payload: dict[str, Any] = _json(nullable=False, default=dict)
    generated_at: datetime = _created()


class SectionView(SQLModel, table=True):
    __tablename__ = "section_view"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    staff_id: str = Field(foreign_key="staff.id")
    section: str  # Section
    opened_at: datetime = _created()


class SectionApproval(SQLModel, table=True):
    __tablename__ = "section_approval"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    section: str  # Section
    staff_id: str = Field(foreign_key="staff.id")
    approved_at: datetime = _created()


class Diagnosis(SQLModel, table=True):
    __tablename__ = "diagnosis"
    id: str = Field(default_factory=new_id, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    staff_id: str = Field(foreign_key="staff.id")
    codes: list[dict[str, Any]] = _json(nullable=False, default=list)  # [{system, code, display}]
    text: str | None = None
    created_at: datetime = _created()


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: int | None = Field(default=None, primary_key=True)  # autoincrement
    ts: datetime = _created()
    actor: str  # kiosk:<id> | staff:<id> | system
    action: str
    entity: str
    entity_id: str | None = None
    details: dict[str, Any] = _json(nullable=False, default=dict)
    prev_hash: str
    hash: str


class Outbox(SQLModel, table=True):
    __tablename__ = "outbox"
    id: str = Field(default_factory=new_id, primary_key=True)
    kind: str = "fhir_bundle"
    session_id: str = Field(foreign_key="session.id")
    patient_id: str = Field(foreign_key="patient.id")
    payload: dict[str, Any] = _json(nullable=False, default=dict)
    idempotency_key: str = Field(unique=True)
    status: str = "pending"  # OutboxStatus
    attempts: int = 0
    last_error: str | None = None
    next_attempt_at: datetime = _created()
    created_at: datetime = _created()
    sent_at: datetime | None = _ts()


class PatientKey(SQLModel, table=True):
    __tablename__ = "patient_key"
    patient_id: str = Field(primary_key=True, foreign_key="patient.id")
    wrapped_key: str | None = None  # base64(nonce(12) + ciphertext); cleared on erase
    created_at: datetime = _created()
    destroyed_at: datetime | None = _ts()


class Setting(SQLModel, table=True):
    __tablename__ = "setting"
    key: str = Field(primary_key=True)  # known: island_mode (bool)
    value: Any = _json(nullable=True)


ALL_TABLES: list[type[SQLModel]] = [
    Staff,
    Patient,
    Session,
    Consent,
    Token,
    Answer,
    Fact,
    Document,
    Readback,
    Alert,
    Summary,
    SectionView,
    SectionApproval,
    Diagnosis,
    AuditLog,
    Outbox,
    PatientKey,
    Setting,
]
