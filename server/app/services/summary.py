"""Doctor summary (CONTRACTS.md §10.5, shape §11.1).

Everything except the HPI narrative is rendered by templates from structured facts (rule 4). The HPI
narrative comes from NLP `/summarize` (grounded, max 3 sentences) and falls back to joining fact texts.
"""

import hashlib
import json
from typing import Any

import httpx
from sqlmodel import Session as DB
from sqlmodel import col, select

from app.config import settings
from app.enums import SECTION_DISPLAY_ORDER, AlertStatus, Section, SourceType, Trust
from app.ids import as_utc, iso_z, utcnow
from app.models import Alert, Answer, Document, Fact, Patient, SectionApproval, SectionView, Session, Summary
from app.services import graph, tokens

TITLES = {
    "complaint": "Chief complaint",
    "hpi": "History of present illness",
    "allergies": "Allergies",
    "drugs": "Medicines",
    "pmh": "Past history",
    "labs": "Lab results",
    "family": "Family history",
    "personal": "Personal history",
    "ros": "Review of systems",
    "ayush": "Ayurveda (AYUSH)",
}
CARRY_SECTIONS = (Section.allergies.value, Section.drugs.value, Section.pmh.value, Section.family.value)
NARRATIVE_SECTIONS = (Section.complaint.value, Section.hpi.value, Section.ros.value)
SUMMARIZE_TIMEOUT_SEC = 20


# ---------------------------------------------------------------- facts


def session_facts(db: DB, session_id: str) -> list[Fact]:
    return list(db.exec(select(Fact).where(Fact.session_id == session_id).order_by(col(Fact.created_at))))


def fact_flags(f: Fact) -> list[str]:
    v = f.value if isinstance(f.value, dict) else {}
    flags = []
    if v.get("readable") is False:
        flags.append("unreadable")
    if v.get("patient_disputed"):
        flags.append("patient_disputed")
    if v.get("patient_unsure"):
        flags.append("patient_unsure")
    if f.source_type == SourceType.carried:
        flags.append("carried")
    return flags


def _found_in_documents(f: Fact) -> bool:
    return f.section == Section.drugs and f.trust == Trust.from_report


def _doctor_notes(db: DB, facts: list[Fact]) -> dict[str, str]:
    """AYUSH answer facts → the question's Sanskrit `doctor_note` (doctor side only)."""
    notes: dict[str, str] = {}
    for f in facts:
        if f.section == Section.ayush and f.source_type == SourceType.answer and f.source_id:
            answer = db.get(Answer, f.source_id)
            found = graph.get_graph().question(answer.question_id) if answer else None
            if found and found[1].get("doctor_note"):
                notes[f.id] = found[1]["doctor_note"]
    return notes


def item(f: Fact, doctor_note: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "fact_id": f.id,
        "text": f.text_en,
        "trust": f.trust,
        "patient_words": f.patient_words,
        "flags": fact_flags(f),
    }
    if f.section == Section.drugs:
        out["found_in_documents"] = _found_in_documents(f)
    if f.source_type == SourceType.document and f.source_id:
        out["source"] = {"document_id": f.source_id, "bbox": f.bbox}
    if doctor_note:
        out["doctor_note"] = doctor_note
    return out


def carry_forward(db: DB, session: Session) -> int:
    """§10.4: copy the patient's doctor-verified allergies/drugs/pmh/family from earlier sessions (once)."""
    previous = db.exec(
        select(Fact)
        .where(
            Fact.patient_id == session.patient_id,
            Fact.session_id != session.id,
            Fact.trust == Trust.doctor_verified,
            col(Fact.section).in_(CARRY_SECTIONS),
        )
        .order_by(col(Fact.created_at).desc())
    ).all()
    seen: set[tuple[str, str]] = set()
    copied = 0
    for f in previous:
        if (f.section, f.text_en) in seen:
            continue
        seen.add((f.section, f.text_en))
        db.add(
            Fact(
                session_id=session.id,
                patient_id=session.patient_id,
                section=f.section,
                key=f.key,
                value=f.value,
                text_en=f.text_en,
                patient_words=f.patient_words,
                trust=Trust.doctor_verified.value,
                source_type=SourceType.carried.value,
                source_id=f.id,
                bbox=f.bbox,
                verified_by=f.verified_by,
                verified_at=f.verified_at,
            )
        )
        copied += 1
    if copied:
        db.flush()
    return copied


# ---------------------------------------------------------------- critical strip


def _allergy_text(f: Fact, has_detail: bool) -> str | None:
    v = f.value if isinstance(f.value, dict) else {}
    if f.source_type == SourceType.answer and f.key == "allergy":
        if v.get("value") is False:
            return "No known allergies (patient said)"
        return None if has_detail else "Allergy reported — details not given"
    if f.source_type == SourceType.answer and f.key == "allergy_detail":
        if v.get("patient_unsure"):
            return "Allergy reported — name not remembered"
        return str(v.get("value") or f.text_en)
    return f.text_en


def critical(db: DB, session: Session, facts: list[Fact]) -> dict[str, Any]:
    allergy_facts = [f for f in facts if f.section == Section.allergies]
    has_detail = any(f.key == "allergy_detail" for f in allergy_facts)
    allergies = []
    for f in allergy_facts:  # rule 12: always shown, whatever the trust
        text = _allergy_text(f, has_detail)
        if text:
            allergies.append({"fact_id": f.id, "text": text, "trust": f.trust})
    alerts = db.exec(
        select(Alert)
        .where(Alert.session_id == session.id, Alert.status != AlertStatus.downgraded)
        .order_by(col(Alert.created_at))
    ).all()
    red_flags = [{"alert_id": a.id, "text": a.reason_text, "level": a.level, "status": a.status} for a in alerts]
    abnormal = [
        {"fact_id": f.id, "text": f.text_en, "trust": f.trust}
        for f in facts
        if f.section == Section.labs
        and f.trust != Trust.rejected
        and str((f.value or {}).get("flag", "")).lower() in {"low", "high"}
    ]
    return {"allergies": allergies, "red_flags": red_flags, "abnormal_labs": abnormal}


# ---------------------------------------------------------------- narrative


def _narrative_input(facts: list[Fact]) -> list[dict[str, Any]]:
    return [
        {"section": f.section, "key": f.key, "value": f.value, "text_en": f.text_en}
        for f in facts
        if f.section in NARRATIVE_SECTIONS and f.trust != Trust.rejected
    ]


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def narrative(facts_in: list[dict[str, Any]]) -> tuple[str, bool]:
    """(text, ai_generated). Falls back to joined fact texts if the NLP service is unavailable."""
    fallback = "; ".join(f["text_en"] for f in facts_in)
    if not facts_in:
        return "", False
    try:
        res = httpx.post(
            f"{settings.nlp_url}/summarize", json={"language": "en", "facts": facts_in}, timeout=SUMMARIZE_TIMEOUT_SEC
        )
        res.raise_for_status()
        out = res.json()
    except (httpx.HTTPError, ValueError):
        return fallback, False
    text = str(out.get("narrative") or "").strip()
    if not text or out.get("fallback_used"):
        return text or fallback, False
    return text, True


# ---------------------------------------------------------------- build


def latest(db: DB, session_id: str) -> Summary | None:
    return db.exec(
        select(Summary).where(Summary.session_id == session_id).order_by(col(Summary.version).desc())
    ).first()


def build(db: DB, session: Session) -> dict[str, Any]:
    """The §11.1 payload (without version/generated_at). Copies carried facts on the first build."""
    if latest(db, session.id) is None:
        carry_forward(db, session)
    facts = session_facts(db, session.id)
    patient = db.get(Patient, session.patient_id)
    token = tokens.latest_token(db, session.id)
    notes = _doctor_notes(db, facts)
    visible = [f for f in facts if f.trust != Trust.rejected]

    prev = latest(db, session.id)
    facts_in = _narrative_input(facts)
    hpi_hash = _hash(facts_in)
    if prev and prev.payload.get("_hpi_hash") == hpi_hash:
        hpi_text, hpi_ai = prev.payload.get("_narrative", ""), bool(prev.payload.get("_narrative_ai"))
    else:
        hpi_text, hpi_ai = narrative(facts_in)

    opened = set(db.exec(select(SectionView.section).where(SectionView.session_id == session.id)).all())
    approved = set(db.exec(select(SectionApproval.section).where(SectionApproval.session_id == session.id)).all())
    sections = []
    for sec in SECTION_DISPLAY_ORDER:
        sec_facts = [f for f in visible if f.section == sec]
        if sec == Section.drugs:  # current medicines first; report-only ones grouped after, never merged
            sec_facts.sort(key=_found_in_documents)
        if not sec_facts and not (sec == Section.hpi and hpi_text):
            continue
        entry: dict[str, Any] = {
            "key": sec.value,
            "title": TITLES[sec.value],
            "opened": sec.value in opened,
            "approved": sec.value in approved,
            "items": [item(f, notes.get(f.id)) for f in sec_facts],
        }
        if sec == Section.hpi:
            entry["narrative"] = hpi_text
            entry["narrative_ai"] = hpi_ai
        sections.append(entry)

    docs = db.exec(select(Document).where(Document.session_id == session.id)).all()
    docs = sorted(docs, key=lambda d: (not d.pinned, -(d.doc_date.toordinal() if d.doc_date else 0), d.page_no))
    opened_at = as_utc(session.opened_by_doctor_at) if session.opened_by_doctor_at else None
    return {
        "session_id": session.id,
        "patient": {
            "id": patient.id,
            "hospital_id": patient.hospital_id,
            "name": patient.name,
            "age": patient.age,
            "sex": patient.sex,
            "language": patient.language,
            "abha_number": patient.abha_number,
        },
        "informant": {"type": session.informant, "relation": session.informant_relation},
        "token": {"display": token.display, "department": token.department} if token else None,
        "critical": critical(db, session, facts),
        "sections": sections,
        "documents": [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "doc_date": d.doc_date.isoformat() if d.doc_date else None,
                "pinned": d.pinned,
                "image_url": f"/api/documents/{d.id}/image",
                "status": d.status,
            }
            for d in docs
        ],
        "new_since_opened": [
            {"fact_id": f.id, "section": f.section, "text": f.text_en}
            for f in visible
            if opened_at and as_utc(f.created_at) > opened_at
        ],
        "_hpi_hash": hpi_hash,
        "_narrative": hpi_text,
        "_narrative_ai": hpi_ai,
    }


def store_if_changed(db: DB, session: Session) -> tuple[Summary, bool]:
    """Build; store a new version only when content changed. Returns (summary, is_new). Does not commit."""
    payload = build(db, session)
    prev = latest(db, session.id)
    if prev and _hash(prev.payload) == _hash(payload):
        return prev, False
    row = Summary(
        session_id=session.id, version=(prev.version + 1) if prev else 1, payload=payload, generated_at=utcnow()
    )
    db.add(row)
    db.flush()
    return row, True


def public(summary: Summary) -> dict[str, Any]:
    """§11.1 wire shape: internal `_` keys stripped, version + generated_at added."""
    body = {k: v for k, v in summary.payload.items() if not k.startswith("_")}
    return {
        "session_id": body.pop("session_id"),
        "version": summary.version,
        "generated_at": iso_z(summary.generated_at),
        **body,
    }
