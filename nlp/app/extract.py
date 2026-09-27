"""Schema-constrained slot extraction (`POST /extract`): Ollama with a JSON Schema built from the request's slots.

The model only reads the patient's answer to ONE question from the YAML graph; it never asks or invents questions.
Durations come from the rule-based `normalize()` whenever it finds one; red flags are never decided here.
"""

import json
import logging
from functools import lru_cache
from typing import Any, Literal

import httpx
import yaml
from pydantic import BaseModel

from app import negation
from app.config import settings
from app.normalize import normalize, to_days

log = logging.getLogger("nlp.extract")

SlotType = Literal["string", "enum", "bool", "number", "duration_days", "scale_0_10", "list_enum", "list_string"]

OLLAMA_TIMEOUT_SEC = 90.0  # a cold model load takes ~30 s on the M1

SYSTEM_PROMPT = (
    "You extract facts from a patient's answer to one clinical question. Return only JSON that matches the schema. "
    "Use null for anything the patient did not say. If the patient denies something (for example 'nahi', 'नहीं', "
    "'no'), set it to false. Never guess, never diagnose, never add fields."
)


class SlotSpec(BaseModel):
    name: str
    type: SlotType
    enum: list[str] | None = None


class ExtractIn(BaseModel):
    question_id: str
    language: Literal["hi", "en"]
    text: str
    question_text_en: str
    slots: list[SlotSpec]


class ExtractOut(BaseModel):
    slots: dict[str, Any]
    status: Literal["confident", "uncertain"]
    notes: list[str]


class InvalidOutput(ValueError):
    """The model's reply does not match the schema."""


# --------------------------------------------------------------------------------------------------------------------
# Schema and prompt
# --------------------------------------------------------------------------------------------------------------------


def slot_schema(slot: SlotSpec) -> dict[str, Any]:
    """JSON Schema for one slot; every slot is nullable."""
    if slot.type in ("enum", "list_enum") and slot.enum:
        item: dict[str, Any] = {"type": "string", "enum": list(slot.enum)}
    else:
        item = {"type": "string"}
    if slot.type == "enum" and slot.enum:
        return {"type": ["string", "null"], "enum": [*slot.enum, None]}
    if slot.type in ("list_enum", "list_string"):
        return {"type": ["array", "null"], "items": item}
    return {
        "string": {"type": ["string", "null"]},
        "enum": {"type": ["string", "null"]},  # enum without choices: free text
        "bool": {"type": ["boolean", "null"]},
        "number": {"type": ["number", "null"]},
        "duration_days": {"type": ["integer", "null"]},
        "scale_0_10": {"type": ["integer", "null"], "minimum": 0, "maximum": 10},
    }[slot.type]


def build_schema(slots: list[SlotSpec]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {s.name: slot_schema(s) for s in slots},
        "required": [s.name for s in slots],
        "additionalProperties": False,
    }


@lru_cache
def choice_labels() -> dict[str, dict[str, str]]:
    """{slot name: {choice value: "English label, Hindi label"}} from content/questions/*.yaml.

    The request carries only enum values ("knee"); the labels ("Knee, घुटना") let a small model map "ghutne" → knee.
    """
    labels: dict[str, dict[str, str]] = {}
    for path in sorted((settings.content_dir / "questions").glob("*.yaml")):
        for q in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("questions", []):
            slot = (q.get("slot") or {}).get("name")
            for c in q.get("choices") or []:
                if slot and isinstance(c.get("value"), str):
                    text = ", ".join(str(c[k]) for k in ("en", "hi") if c.get(k))
                    labels.setdefault(slot, {}).setdefault(c["value"], text)
    return labels


def _options(slot: SlotSpec) -> str:
    known = choice_labels().get(slot.name, {})
    return "; ".join(f"{v} ({known[v]})" if v in known else v for v in slot.enum or [])


def _describe(slot: SlotSpec) -> str:
    options = _options(slot)
    return {
        "string": "text",
        "enum": f"one of: {options}" if options else "text",
        "bool": "true or false",
        "number": "a number",
        "duration_days": "number of days (1 week = 7, 1 month = 30, 1 year = 365)",
        "scale_0_10": "whole number from 0 to 10",
        "list_enum": f"list, each item one of: {options}" if options else "list of text items",
        "list_string": "list of text items",
    }[slot.type]


def user_message(question: str, slots: list[SlotSpec], answer: str) -> str:
    lines = "\n".join(f"- {s.name}: {_describe(s)}" for s in slots)
    return f"Question: {question}\nSlots:\n{lines}\nPatient's answer: {answer}"


_FEW_SHOT: list[tuple[str, list[SlotSpec], str, dict[str, Any]]] = [
    (  # Hindi (Devanagari): said yes to swelling, denied injury, fever not mentioned
        "Tell us about your pain.",
        [
            SlotSpec(name="site", type="enum", enum=["knee", "back", "shoulder", "hip"]),
            SlotSpec(name="swelling", type="bool"),
            SlotSpec(name="fever", type="bool"),
            SlotSpec(name="injury", type="bool"),
        ],
        "कंधे में सूजन है, चोट नहीं लगी",
        {"site": "shoulder", "swelling": True, "fever": None, "injury": False},
    ),
    (  # Romanised Hindi: only the denied slot is false; swelling was not mentioned, so it stays null
        "Tell us about your pain.",
        [
            SlotSpec(name="site", type="enum", enum=["knee", "back", "shoulder", "hip"]),
            SlotSpec(name="duration_days", type="duration_days"),
            SlotSpec(name="fever", type="bool"),
            SlotSpec(name="swelling", type="bool"),
        ],
        "do hafte se kamar mein dard hai, bukhar nahi hai",
        {"site": "back", "duration_days": 14, "fever": False, "swelling": None},
    ),
    (  # English: unasked details (swelling) are not added; unsaid slots are null
        "Which joint hurts the most?",
        [
            SlotSpec(name="site", type="enum", enum=["knee", "back", "shoulder", "hip"]),
            SlotSpec(name="severity", type="scale_0_10"),
        ],
        "my right knee, it is a bit swollen too",
        {"site": "knee", "severity": None},
    ),
]


def build_messages(req: ExtractIn) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for question, slots, answer, reply in _FEW_SHOT:
        messages.append({"role": "user", "content": user_message(question, slots, answer)})
        messages.append({"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)})
    messages.append({"role": "user", "content": user_message(req.question_text_en, req.slots, req.text)})
    return messages


# --------------------------------------------------------------------------------------------------------------------
# Validation of the model's reply
# --------------------------------------------------------------------------------------------------------------------


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def coerce(slot: SlotSpec, v: Any) -> Any:
    """Return the cleaned value, or raise InvalidOutput."""
    if v is None:
        return None
    t = slot.type
    if t == "bool" and isinstance(v, bool):
        return v
    if t == "number" and _is_number(v):
        return v
    if t == "duration_days" and _is_number(v) and v >= 0:
        return to_days(v)
    if t == "scale_0_10" and _is_number(v) and float(v).is_integer() and 0 <= v <= 10:
        return int(v)
    if t in ("string", "enum") and isinstance(v, str):
        v = v.strip()
        if t == "enum" and slot.enum and v not in slot.enum:
            raise InvalidOutput(f"{slot.name}: {v!r} is not one of {slot.enum}")
        return v or None
    if t in ("list_enum", "list_string") and isinstance(v, list) and all(isinstance(x, str) for x in v):
        items = list(dict.fromkeys(x.strip() for x in v if x.strip()))
        if t == "list_enum" and slot.enum and any(x not in slot.enum for x in items):
            raise InvalidOutput(f"{slot.name}: {items!r} not all in {slot.enum}")
        return items
    raise InvalidOutput(f"{slot.name}: {v!r} is not a valid {t}")


def parse_reply(content: str, slots: list[SlotSpec]) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise InvalidOutput(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidOutput("not a JSON object")
    return {s.name: coerce(s, data.get(s.name)) for s in slots}  # unknown keys are dropped


# --------------------------------------------------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------------------------------------------------


async def ollama_chat(messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "format": schema,
        "stream": False,
        "options": {"temperature": 0},
    }
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SEC) as client:
        r = await client.post(f"{settings.ollama_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        return str(r.json()["message"]["content"])


# --------------------------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------------------------


async def extract(req: ExtractIn) -> ExtractOut:
    empty: dict[str, Any] = {s.name: None for s in req.slots}
    if not req.text.strip():
        return ExtractOut(slots=empty, status="uncertain", notes=["empty text"])

    notes: list[str] = []
    uncertain = False
    slots = dict(empty)
    messages, schema = build_messages(req), build_schema(req.slots)
    try:
        for attempt in (1, 2):  # one retry on invalid JSON
            content = await ollama_chat(messages, schema)
            try:
                slots = parse_reply(content, req.slots)
                break
            except InvalidOutput as exc:
                log.warning("extract %s: invalid model output (attempt %d): %s", req.question_id, attempt, exc)
                if attempt == 2:
                    notes.append(f"model output invalid after retry: {exc}")
                    uncertain = True
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("extract %s: Ollama call failed: %s", req.question_id, exc)
        notes.append("language model unavailable")
        uncertain = True

    # Durations: the rule-based parser beats the model ("teen mahine" = 90, never 3).
    durations = normalize(req.text, req.language)["durations"]
    for s in req.slots:
        if s.type != "duration_days" or not durations:
            continue
        phrase, days = durations[0]["phrase"], durations[0]["days"]
        if slots[s.name] is None:
            notes.append(f"{s.name} filled from '{phrase}'")
        elif slots[s.name] != days:
            notes.append(f"{s.name} {slots[s.name]} replaced by {days} from '{phrase}'")
        slots[s.name] = days

    # Negation double-check: "bukhar nahi hai" read as fever=true → null + uncertain.
    slots, neg_notes, neg_uncertain = negation.check(req.text, slots)
    notes += neg_notes
    uncertain = uncertain or neg_uncertain

    if all(v is None for v in slots.values()) and not uncertain:
        notes.append("nothing extracted")
        uncertain = True
    return ExtractOut(slots=slots, status="uncertain" if uncertain else "confident", notes=notes)
