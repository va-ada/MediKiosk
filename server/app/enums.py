"""Every enum from CONTRACTS.md §2. Values are the exact wire strings."""

from enum import Enum


class Sex(str, Enum):
    M = "M"
    F = "F"
    O = "O"


class Language(str, Enum):
    hi = "hi"
    en = "en"


class Role(str, Enum):
    doctor = "doctor"
    nurse = "nurse"
    desk = "desk"
    admin = "admin"


class Department(str, Enum):
    general = "general"
    ayurveda = "ayurveda"


class Informant(str, Enum):
    self = "self"
    proxy = "proxy"


class LegalBasis(str, Enum):
    consent = "consent"
    medical_emergency = "medical_emergency"


class SessionStatus(str, Enum):
    identifying = "identifying"
    consented = "consented"
    triaged = "triaged"
    history = "history"
    documents = "documents"
    verifying = "verifying"
    submitted = "submitted"
    with_doctor = "with_doctor"
    closed = "closed"


class Lane(str, Enum):
    emergency = "emergency"
    priority = "priority"
    normal = "normal"


class TokenStatus(str, Enum):
    waiting = "waiting"
    called = "called"
    in_ = "in"
    no_show = "no_show"
    absent = "absent"
    done = "done"
    referred = "referred"


class Outcome(str, Enum):
    out = "out"
    recheck = "recheck"
    refer = "refer"
    followup = "followup"


class AnswerSource(str, Enum):
    voice = "voice"
    tap = "tap"
    staff = "staff"


class AnswerStatus(str, Enum):
    confident = "confident"
    uncertain = "uncertain"


class Section(str, Enum):
    complaint = "complaint"
    hpi = "hpi"
    pmh = "pmh"
    drugs = "drugs"
    allergies = "allergies"
    family = "family"
    personal = "personal"
    ros = "ros"
    labs = "labs"
    ayush = "ayush"


SECTION_DISPLAY_ORDER: list[Section] = [
    Section.complaint,
    Section.hpi,
    Section.allergies,
    Section.drugs,
    Section.pmh,
    Section.labs,
    Section.family,
    Section.personal,
    Section.ros,
    Section.ayush,
]


class Trust(str, Enum):
    patient_said = "patient_said"
    from_report = "from_report"
    doctor_verified = "doctor_verified"
    rejected = "rejected"


class SourceType(str, Enum):
    answer = "answer"
    document = "document"
    doctor = "doctor"
    carried = "carried"


class DocType(str, Enum):
    lab_report = "lab_report"
    prescription = "prescription"
    discharge_summary = "discharge_summary"
    unknown = "unknown"


class DocStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    failed = "failed"


class AlertLevel(str, Enum):
    urgent = "urgent"
    emergency = "emergency"


class AlertSource(str, Enum):
    button = "button"
    rule = "rule"


class AlertStatus(str, Enum):
    open = "open"
    acknowledged = "acknowledged"
    confirmed = "confirmed"
    downgraded = "downgraded"


class ReasonCode(str, Enum):
    chest_pain = "chest_pain"
    breathing = "breathing"
    bleeding = "bleeding"
    unconscious = "unconscious"
    seizure = "seizure"
    stroke_signs = "stroke_signs"
    severe_pain = "severe_pain"
    pregnancy = "pregnancy"
    other = "other"


class ComplaintCode(str, Enum):
    joint_pain = "joint_pain"
    fever = "fever"
    cough = "cough"
    stomach = "stomach"
    headache = "headache"
    chest_pain = "chest_pain"
    breathing = "breathing"
    skin = "skin"
    other = "other"


class ReadbackResponse(str, Enum):
    yes = "yes"
    no = "no"
    not_sure = "not_sure"


class OutboxStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    skipped_no_consent = "skipped_no_consent"
    failed = "failed"


class DeviceMode(str, Enum):
    KIOSK = "KIOSK"
    HALL = "HALL"
    PATIENT_APP = "PATIENT_APP"


class QuestionType(str, Enum):
    choice = "choice"
    multi = "multi"
    yesno = "yesno"
    number = "number"
    duration = "duration"
    scale = "scale"
    free = "free"


class SlotType(str, Enum):
    string = "string"
    enum = "enum"
    bool = "bool"
    number = "number"
    duration_days = "duration_days"
    scale_0_10 = "scale_0_10"
    list_enum = "list_enum"
    list_string = "list_string"
