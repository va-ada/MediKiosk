from functools import lru_cache
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import col, select

from app import audit
from app.auth import kiosk_id
from app.config import settings
from app.db import DbSession
from app.enums import Language, ReadbackResponse, Section, SessionStatus, Trust
from app.errors import ApiError
from app.models import Answer, Fact, Patient, Readback
from app.routers.sessions import get_session_or_404
from app.routers.triage import triage_config
from app.services import graph

router = APIRouter(prefix="/api/sessions", tags=["readback"])

KioskId = Annotated[str, Depends(kiosk_id)]
READBACK_SECTIONS = (Section.complaint.value, Section.hpi.value)  # never drugs, doses or labs
UNITS = {
    "en": ("day", "days", "week", "weeks", "month", "months", "year", "years"),
    "hi": ("दिन", "दिन", "हफ़्ता", "हफ़्ते", "महीना", "महीने", "साल", "साल"),
}


class ReadbackIn(BaseModel):
    fact_id: str
    response: ReadbackResponse


@lru_cache
def templates() -> dict[str, dict[str, str]]:
    return yaml.safe_load((settings.content_dir / "readback_templates.yaml").read_text(encoding="utf-8")) or {}


def human_duration(days: int, lang: str) -> str:
    """90 → "3 months" / "3 महीने": patients judge months more easily than day counts."""
    u = UNITS[lang]
    for limit, size, one, many in ((14, 1, u[0], u[1]), (60, 7, u[2], u[3]), (365, 30, u[4], u[5])):
        if days < limit:
            n = max(1, round(days / size))
            return f"{n} {one if n == 1 else many}"
    n = max(1, round(days / 365))
    return f"{n} {u[6] if n == 1 else u[7]}"


def _labels(fact: Fact, value: Any, db: DbSession) -> tuple[str, str]:
    if fact.key == "chief_complaint":
        c = triage_config().get((fact.value or {}).get("complaint_code"), {})
        return c.get("en", fact.text_en), c.get("hi", fact.text_en)
    answer = db.get(Answer, fact.source_id) if fact.source_id else None
    found = graph.get_graph().question(answer.question_id) if answer else None
    choices = {c["value"]: c for c in (found[1].get("choices") or [])} if found else {}
    values = value if isinstance(value, list) else [value]
    en = ", ".join(str(choices.get(v, {}).get("en", v)) for v in values)
    hi = ", ".join(str(choices.get(v, {}).get("hi", v)) for v in values)
    return en, hi


def render(fact: Fact, lang: str, db: DbSession) -> str:
    tpl = templates().get(fact.key)
    if not tpl:
        return fact.text_en
    value = (fact.value or {}).get("value")
    label_en, label_hi = _labels(fact, value, db)
    fields = {
        "value": value,
        "label_en": label_en,
        "label_hi": label_hi,
        "yesno_en": "Yes" if value else "No",
        "yesno_hi": "हाँ" if value else "नहीं",
        "duration_en": human_duration(value, "en") if isinstance(value, int) else value,
        "duration_hi": human_duration(value, "hi") if isinstance(value, int) else value,
    }
    try:
        return tpl.get(lang, tpl.get("en", "")).format(**fields) or fact.text_en
    except (KeyError, IndexError, ValueError):
        return fact.text_en


def eligible_facts(db: DbSession, session_id: str) -> list[Fact]:
    done = set(db.exec(select(Readback.fact_id).where(Readback.session_id == session_id)).all())
    facts = db.exec(
        select(Fact)
        .where(
            Fact.session_id == session_id, col(Fact.section).in_(READBACK_SECTIONS), Fact.trust == Trust.patient_said
        )
        .order_by(col(Fact.created_at))
    ).all()
    return [
        f
        for f in facts
        if f.id not in done
        and not (f.value or {}).get("patient_unsure")
        and (f.value or {}).get("value", f.value) is not None
    ]


@router.get("/{session_id}/readback")
def get_readback(
    session_id: str, db: DbSession, _kiosk: KioskId, language: Annotated[Language | None, Query()] = None
) -> dict[str, Any]:
    s = get_session_or_404(db, session_id)
    patient = db.get(Patient, s.patient_id)
    lang = language.value if language else (patient.language if patient else "hi")
    if s.status in (SessionStatus.history, SessionStatus.documents):
        s.status = SessionStatus.verifying.value
        db.add(s)
        db.commit()
    return {
        "items": [
            {"fact_id": f.id, "text": render(f, lang, db), "text_en": render(f, "en", db)}
            for f in eligible_facts(db, s.id)
        ]
    }


@router.post("/{session_id}/readback")
def post_readback(session_id: str, body: ReadbackIn, db: DbSession, kiosk: KioskId) -> dict[str, bool]:
    s = get_session_or_404(db, session_id)
    fact = db.get(Fact, body.fact_id)
    if fact is None or fact.session_id != s.id:
        raise ApiError(404, "not_found", "Fact not found in this session")
    if fact.section not in READBACK_SECTIONS:
        raise ApiError(422, "validation_error", "Only complaint and history facts are read back")
    rb = Readback(session_id=s.id, fact_id=fact.id, response=body.response.value)
    db.add(rb)
    value = {k: v for k, v in (fact.value or {}).items() if k not in ("patient_disputed", "patient_unsure")}
    if body.response == ReadbackResponse.no:
        value["patient_disputed"] = True
    elif body.response == ReadbackResponse.not_sure:
        value["patient_unsure"] = True
    fact.value = value  # reassign: JSON columns are not mutation-tracked
    db.add(fact)
    db.flush()
    audit.record(
        db,
        f"kiosk:{kiosk}",
        "readback.create",
        "readback",
        rb.id,
        {"fact_id": fact.id, "response": body.response.value},
    )
    db.commit()
    return {"ok": True}
