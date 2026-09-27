"""Adaptive question graph (CONTRACTS.md §9.1) and answer → fact recording.

Questions come only from `content/questions/*.yaml` (rule 2). A session walks its triage pathway
from `start`, skipping answered questions and following `next` rules over every slot answered so far
(including triage slots); ayurveda sessions then continue into `ayush.yaml` if it exists.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import Session as DB
from sqlmodel import col, select

from app import audit
from app.config import settings
from app.enums import AnswerStatus, Department, Section, SessionStatus, SlotType, SourceType, Trust
from app.errors import ApiError
from app.models import Alert, Answer, Fact, Readback, Session
from app.services import redflags

MAX_STEPS = 500  # guards against a cyclic graph
NONE_CHOICE, UNSURE_CHOICE = "none", "not_sure"


@dataclass
class Pathway:
    id: str
    start: str
    questions: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class Graph:
    pathways: dict[str, Pathway] = field(default_factory=dict)

    @classmethod
    def from_docs(cls, docs: list[dict[str, Any]]) -> "Graph":
        g = cls()
        for doc in docs:
            g.pathways[doc["id"]] = Pathway(doc["id"], doc["start"], {q["id"]: q for q in doc["questions"]})
        return g

    @classmethod
    def from_dir(cls, path: Path) -> "Graph":
        docs = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(path.glob("*.yaml"))]
        return cls.from_docs([d for d in docs if isinstance(d, dict) and d.get("questions")])

    def question(self, qid: str) -> tuple[Pathway, dict[str, Any]] | None:
        for p in self.pathways.values():
            if qid in p.questions:
                return p, p.questions[qid]
        return None


_override: Graph | None = None  # tests install a tiny graph here


@lru_cache
def _loaded() -> Graph:
    return Graph.from_dir(settings.content_dir / "questions")


def get_graph() -> Graph:
    return _override or _loaded()


def set_graph(graph: Graph | None) -> None:
    global _override
    _override = graph


# ---------------------------------------------------------------- walking the graph


def session_pathways(session: Session) -> list[Pathway]:
    g = get_graph()
    ids = [session.pathway] if session.pathway else []
    if session.department == Department.ayurveda and "ayush" in g.pathways and "ayush" not in ids:
        ids.append("ayush")
    return [g.pathways[i] for i in ids if i in g.pathways]


def confident_answers(db: DB, session_id: str) -> list[Answer]:
    return list(
        db.exec(
            select(Answer)
            .where(Answer.session_id == session_id, Answer.status == AnswerStatus.confident)
            .order_by(col(Answer.created_at))
        )
    )


def session_slots(db: DB, session_id: str) -> dict[str, Any]:
    """Every confidently answered slot so far, triage included; later answers win."""
    slots: dict[str, Any] = {}
    for a in confident_answers(db, session_id):
        slots.update(a.slots or {})
    return slots


def condition_holds(cond: dict[str, Any], slots: dict[str, Any]) -> bool:
    if cond.get("slot") not in slots or slots[cond["slot"]] is None:
        return False
    v = slots[cond["slot"]]
    try:
        if "is" in cond:
            return v == cond["is"]
        if "in" in cond:
            options = cond["in"]
            return bool(set(v) & set(options)) if isinstance(v, list) else v in options
        if "gte" in cond:
            return v >= cond["gte"]
        if "lte" in cond:
            return v <= cond["lte"]
    except TypeError:
        return False
    return False


def resolve_next(question: dict[str, Any], slots: dict[str, Any]) -> str:
    nxt = question.get("next", "end")
    if isinstance(nxt, str):
        return nxt
    for rule in nxt:
        if "if" not in rule or condition_holds(rule["if"], slots):
            return rule["goto"]
    return "end"


def _walk(pathway: Pathway, answered: set[str], slots: dict[str, Any]) -> str | None:
    """First unanswered question on this pathway's live path, or None when the pathway is finished."""
    cur = pathway.start
    for _ in range(MAX_STEPS):
        if cur == "end" or cur not in pathway.questions:
            return None
        if cur not in answered:
            return cur
        cur = resolve_next(pathway.questions[cur], slots)
    raise ApiError(500, "graph_cycle", f"Question graph {pathway.id} has a cycle")


def _remaining_from(pathway: Pathway, qid: str, slots: dict[str, Any]) -> int:
    """Questions left on the path from `qid` (inclusive), assuming unanswered slots take default rules."""
    n, cur = 0, qid
    for _ in range(MAX_STEPS):
        if cur == "end" or cur not in pathway.questions:
            break
        n += 1
        cur = resolve_next(pathway.questions[cur], slots)
    return n


def next_question(db: DB, session: Session) -> tuple[dict[str, Any], dict[str, int]] | None:
    """(question, progress) for the next unanswered question, or None when the history is done."""
    pathways = session_pathways(session)
    answered = {a.question_id for a in confident_answers(db, session.id)}
    slots = session_slots(db, session.id)
    for i, p in enumerate(pathways):
        qid = _walk(p, answered, slots)
        if qid is None:
            continue
        remaining = _remaining_from(p, qid, slots) + sum(_remaining_from(q, q.start, slots) for q in pathways[i + 1 :])
        done = sum(1 for q in pathways for a in answered if a in q.questions)
        return p.questions[qid], {"answered": done, "remaining_estimate": remaining}
    return None


def render(question: dict[str, Any], language: str, progress: dict[str, int] | None = None) -> dict[str, Any]:
    """Question (§11.4) in the requested language. `doctor_note` (Sanskrit terms) is never sent to the kiosk."""
    lang = "hi" if language == "hi" else "en"
    choices = [
        {
            "value": c["value"],
            "label": c.get(lang) or c.get("en"),
            "en": c.get("en"),
            "hi": c.get("hi"),
            "icon": c.get("icon"),
        }
        for c in question.get("choices") or []
    ]
    return {
        "id": question["id"],
        "type": question["type"],
        "section": question["section"],
        "text": question.get(f"text_{lang}") or question["text_en"],
        "text_en": question["text_en"],
        "audio": question["id"],
        "choices": choices,
        "slot": {"name": question["slot"]["name"], "type": question["slot"]["type"]},
        "allow_voice": lang in settings.voice_languages.split(","),
        "progress": progress or {"answered": 0, "remaining_estimate": 0},
    }


# ---------------------------------------------------------------- answers → facts


def _bad(question: dict[str, Any], why: str) -> ApiError:
    return ApiError(422, "validation_error", f"{question['id']}: {why}")


def _choice_values(question: dict[str, Any]) -> list[Any]:
    return [c["value"] for c in question.get("choices") or []]


def coerce_value(question: dict[str, Any], value: Any) -> tuple[Any, bool]:
    """Validate a tapped/extracted value against the slot type. Returns (slot_value, patient_unsure)."""
    stype = question["slot"]["type"]
    choices = _choice_values(question)
    if isinstance(value, str) and value == UNSURE_CHOICE and UNSURE_CHOICE in choices:
        return None, True
    if stype == SlotType.enum:
        if value not in choices:
            raise _bad(question, f"{value!r} is not one of {choices}")
        return value, False
    if stype == SlotType.bool:
        if isinstance(value, bool):
            return value, False
        if isinstance(value, str) and value.lower() in {"yes", "true", "no", "false"}:
            return value.lower() in {"yes", "true"}, False
        raise _bad(question, "expected true or false")
    if stype in (SlotType.number, SlotType.duration_days, SlotType.scale_0_10):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _bad(question, "expected a number")
        if stype == SlotType.number:
            return value, False
        n = round(value)
        hi = 10 if stype == SlotType.scale_0_10 else 36500
        if not 0 <= n <= hi:
            raise _bad(question, f"expected 0–{hi}")
        return n, False
    if stype == SlotType.list_enum:
        items = value if isinstance(value, list) else [value]
        bad = [v for v in items if v not in choices]
        if bad or not items:
            raise _bad(question, f"{bad or 'empty'} not in {choices}")
        items = list(dict.fromkeys(items))
        if NONE_CHOICE in items:
            items = [NONE_CHOICE]  # "none of these" wins over accidental extra taps
        return items, False
    if stype == SlotType.list_string:
        if value == NONE_CHOICE:
            return [], False
        items = value if isinstance(value, list) else str(value).split(",")
        items = [" ".join(str(v).split()) for v in items if str(v).strip()]
        if not items:
            raise _bad(question, "expected at least one item")
        return items, False
    if stype == SlotType.string:
        if value == NONE_CHOICE:
            return NONE_CHOICE, False
        text = " ".join(str(value or "").split())
        if not text:
            raise _bad(question, "expected some text")
        return text[:500], False
    raise _bad(question, f"unknown slot type {stype}")


def _label(slot_name: str) -> str:
    return slot_name.replace("_", " ").capitalize()


def _choice_en(question: dict[str, Any], value: Any) -> str:
    for c in question.get("choices") or []:
        if c["value"] == value:
            return c.get("en") or str(value)
    return str(value)


def fact_text(question: dict[str, Any], value: Any, unsure: bool) -> str:
    """Doctor-facing English text built from templates — never from the model (rule 4)."""
    qtype, name = question["type"], question["slot"]["name"]
    if unsure:
        return f"{_label(name)}: patient not sure"
    if qtype == "yesno":
        return f"{'Yes' if value else 'No'}: {question['text_en']}"
    if qtype == "duration":
        return f"Duration: {value} day{'s' if value != 1 else ''}"
    if qtype == "scale":
        return f"{_label(name)}: {value}/10"
    if qtype == "choice":
        return f"{_label(name)}: {_choice_en(question, value)}"
    if qtype == "multi":
        return f"{_label(name)}: {', '.join(_choice_en(question, v) for v in value)}"
    if isinstance(value, list):
        return f"{_label(name)}: {', '.join(value) if value else 'none'}"
    return f"{_label(name)}: {value}"


def _drug_value(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "name_as_written": name,
        "dose": None,
        "frequency": None,
        "duration": None,
        "matched": False,
        "found_in_documents": False,
    }


def _facts_for(
    session: Session, question: dict[str, Any], answer: Answer, value: Any, unsure: bool, raw_text: str | None
) -> list[Fact]:
    name, section = question["slot"]["name"], question["section"]
    base = {
        "session_id": session.id,
        "patient_id": session.patient_id,
        "section": section,
        "key": name,
        "patient_words": raw_text,
        "trust": Trust.patient_said.value,
        "source_type": SourceType.answer.value,
        "source_id": answer.id,
    }
    if section == Section.drugs and isinstance(value, list) and value:
        return [Fact(**base, value=_drug_value(v), text_en=f"Medicine (patient reported): {v}") for v in value]
    fact_value: dict[str, Any] = {"value": value}
    if unsure:
        fact_value["patient_unsure"] = True
    return [Fact(**base, value=fact_value, text_en=fact_text(question, value, unsure))]


def apply_answer(
    db: DB,
    session: Session,
    question: dict[str, Any],
    value: Any,
    source: str,
    raw_text: str | None = None,
    confidence: float | None = None,
    status: str = AnswerStatus.confident.value,
    actor: str | None = None,
) -> tuple[Answer, list[Alert]]:
    """Validate, store the Answer, replace this slot's answer-sourced facts, run red-flag rules. Commits."""
    slot_value, unsure = coerce_value(question, value)
    name = question["slot"]["name"]
    answer = Answer(
        session_id=session.id,
        question_id=question["id"],
        source=source,
        raw_text=raw_text,
        confidence=confidence,
        slots={name: slot_value},
        status=status,
    )
    db.add(answer)
    db.flush()

    old = db.exec(
        select(Fact).where(Fact.session_id == session.id, Fact.key == name, Fact.source_type == SourceType.answer)
    ).all()
    for f in old:  # re-answer (e.g. after resume): the newest answer replaces the old facts
        for rb in db.exec(select(Readback).where(Readback.fact_id == f.id)).all():
            db.delete(rb)  # a read-back of a replaced fact is moot
        db.delete(f)
    db.flush()
    facts = _facts_for(session, question, answer, slot_value, unsure, raw_text)
    db.add_all(facts)
    if session.status == SessionStatus.triaged:
        session.status = SessionStatus.history.value
        db.add(session)
    db.flush()
    audit.record(
        db,
        actor or f"kiosk:{session.kiosk_id}",
        "answer.create",
        "answer",
        answer.id,
        {
            "session_id": session.id,
            "question_id": question["id"],
            "source": source,
            "status": status,
            "fact_ids": [f.id for f in facts],
            "replaced_fact_ids": [f.id for f in old],
        },
    )
    alerts = redflags.evaluate_and_alert(db, session, session_slots(db, session.id))
    db.commit()
    db.refresh(answer)
    return answer, alerts
