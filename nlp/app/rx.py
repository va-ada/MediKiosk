"""Prescription extraction from OCR lines → drug Entities (CONTRACTS §3 drugs shape, `found_in_documents: true`).

A row is a medicine line if it starts with Tab/Cap/Syp/Inj, or a drug from `content/drugs.csv` (generic or brand)
fuzzy-matches (rapidfuzz ≥ 85). Dose, frequency code and duration are parsed by rules. A following row that only
carries directions ("before breakfast x 14 days") is attached to the medicine above it.

Never guessed (CLAUDE.md rule 6): a row read with conf < 0.6, a Tab/Cap line whose drug we can't match, or any
page where OCR produced digit/letter confusions in a medicine line ("4o mg" — typical of handwriting) gives
`readable: false` with dose/frequency/duration left empty.
"""

import csv
import re
from functools import lru_cache

from rapidfuzz import fuzz

from app.config import settings
from app.document import group_rows, union_bbox

MIN_CONF = 0.6
MIN_SCORE = 85
SHORT_ALIAS = 5  # aliases shorter than this ("Pan", "Mox") must match exactly, and only after Tab/Cap/…

_PREFIX_RE = re.compile(
    r"^\W*(?:\d+\s*[.)]\s*)?(tablet|tab|capsule|cap|syrup|syp|injection|inj)\b\.?\s*", re.IGNORECASE
)
_GLUED_PREFIX_RE = re.compile(
    r"^(\W*(?:\d+\s*[.)]\s*)?(?i:tablet|tab|capsule|cap|syrup|syp|injection|inj)\.?)(?=[A-Z])"
)
_DOSE_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mg|mcg|µg|gm|g|ml|tablets?|tabs?|caps?|units?|iu)\b", re.IGNORECASE
)
_FREQ_CODES = {
    "od": "once daily", "bd": "twice daily", "bid": "twice daily", "tds": "three times daily",
    "tid": "three times daily", "qid": "four times daily", "hs": "at bedtime", "sos": "when needed",
    "prn": "when needed", "ac": "before food", "pc": "after food",
}  # fmt: skip
_FREQ_PHRASES = [
    (re.compile(r"\bonce\s+(?:a\s+)?daily\b|\bonce\s+a\s+day\b", re.IGNORECASE), "once daily"),
    (re.compile(r"\btwice\s+(?:a\s+)?daily\b|\btwice\s+a\s+day\b", re.IGNORECASE), "twice daily"),
    (re.compile(r"\b(?:thrice|three\s+times)\s+(?:a\s+)?(?:daily|day)\b", re.IGNORECASE), "three times daily"),
    (re.compile(r"\bbefore\s+(?:food|meals?|breakfast|lunch|dinner)\b", re.IGNORECASE), "before food"),
    (re.compile(r"\bafter\s+(?:food|meals?|breakfast|lunch|dinner)\b", re.IGNORECASE), "after food"),
    (re.compile(r"\bat\s+(?:bed\s*time|night)\b", re.IGNORECASE), "at bedtime"),
]
_FREQ_CODE_RE = re.compile(rf"(?<![\w-])({'|'.join(_FREQ_CODES)})(?![\w-])", re.IGNORECASE)
_DOSING_PATTERN_RE = re.compile(r"(?<![\d-])([01])\s*-\s*([01])\s*-\s*([01])(?![\d-])")  # 1-0-1
_DURATION_RE = re.compile(r"(?:\bx|×|\bfor)\s*(\d+)\s*(days?|d|weeks?|wks?|w|months?|mo)\b", re.IGNORECASE)
_BARE_DURATION_RE = re.compile(r"\b(\d+)\s*(days|weeks|months)\b", re.IGNORECASE)
_UNIT_WORD = {"d": "day", "w": "week", "wk": "week", "mo": "month"}
# A number-like token with OCR digit/letter confusions: "4o", "65o", "l0", "5OO".
_GARBLED_RE = re.compile(r"(?<![\w.])(?=[\dOoIl.]*\d)(?=[\dOoIl.]*[OoIl])[\dOoIl.]{2,}(?![\w.])")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]*|\d+")  # numbers count as words for brands like "Dolo 650"
_PAT_NAMES = {1: "once daily", 2: "twice daily", 3: "three times daily"}


@lru_cache
def drug_aliases() -> list[tuple[str, str, int]]:
    """[(alias_lower, generic, word_count)] from drugs.csv — generic names and brand examples."""
    out: list[tuple[str, str, int]] = []
    with (settings.content_dir / "drugs.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            generic = r["generic"].strip()
            for name in [generic, *(b.strip() for b in (r.get("brand_examples") or "").split(";"))]:
                if name:
                    out.append((name.lower(), generic, len(name.split())))
    return out


def normalise(text: str) -> str:
    """Undo OCR gluing: "TabMetformin500mgBDx30days" → "Tab Metformin 500 mg BD x 30 days"."""
    codes = "|".join(_FREQ_CODES)
    text = " ".join(text.split())
    text = _GLUED_PREFIX_RE.sub(r"\1 ", text)  # TabMetformin → Tab Metformin
    text = re.sub(r"(?<=[A-Za-z]{3})(?=\d)", " ", text)  # Metformin500 → Metformin 500 (keeps "B12")
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)  # 500mg → 500 mg
    text = re.sub(rf"(?<=[a-z])(?=(?:{codes.upper()})(?:x|\b))", " ", text)  # mgSOS → mg SOS (codes are capitals)
    return re.sub(rf"(?<![\w-])({codes})x(?=\s*\d|\b)", r"\1 x", text, flags=re.IGNORECASE)  # BDx → BD x


def match_drug(text: str, allow_short: bool = True) -> tuple[str, str, int] | None:
    """Best drugs.csv match in `text` → (generic, name_as_written, end offset) or None."""
    words = list(_WORD_RE.finditer(text))
    best: tuple[float, int, str, str, int] | None = None
    for alias, generic, k in drug_aliases():
        if len(alias) < SHORT_ALIAS and not allow_short:
            continue
        for i in range(len(words) - k + 1):
            span = words[i : i + k]
            window = text[span[0].start() : span[-1].end()]
            w = window.lower()
            score = 100.0 if w == alias else 0.0 if len(alias) < SHORT_ALIAS else fuzz.ratio(w, alias)
            if score >= MIN_SCORE and (best is None or (score, len(alias)) > (best[0], best[1])):
                best = (score, len(alias), generic, window, span[-1].end())
    return (best[2], best[3], best[4]) if best else None


def _duration(text: str, bare: bool) -> str | None:
    m = _DURATION_RE.search(text) or (_BARE_DURATION_RE.search(text) if bare else None)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    unit = _UNIT_WORD.get(unit.rstrip("s") if unit not in ("d", "w") else unit, unit.rstrip("s"))
    return f"{n} {unit}{'' if n == 1 else 's'}"


def _frequency(text: str) -> str | None:
    found: list[tuple[int, str]] = [(m.start(), _FREQ_CODES[m.group(1).lower()]) for m in _FREQ_CODE_RE.finditer(text)]
    found += [(m.start(), label) for rx, label in _FREQ_PHRASES for m in rx.finditer(text)]
    for m in _DOSING_PATTERN_RE.finditer(text):
        if n := sum(int(g) for g in m.groups()):
            found.append((m.start(), _PAT_NAMES[n]))
    labels: list[str] = []
    for _, label in sorted(found):
        if label not in labels:
            labels.append(label)
    return ", ".join(labels) or None


def _dose(text: str) -> str | None:
    m = _DOSE_RE.search(text)
    if not m:
        return None
    unit = m.group(2).lower()
    unit = {"µg": "mcg", "gm": "g", "tabs": "tab", "tablet": "tab", "tablets": "tab", "caps": "cap"}.get(unit, unit)
    return f"{m.group(1)} {unit}"


def _is_direction(text: str) -> bool:
    """A row that only continues the medicine above: directions, no label ("Advice:", "Follow-up:")."""
    return ":" not in text and bool(
        _FREQ_CODE_RE.search(text) or _DURATION_RE.search(text) or any(rx.search(text) for rx, _ in _FREQ_PHRASES)
    )


def text_en(v: dict) -> str:
    name = v["name"] if v["name_as_written"].lower() == v["name"].lower() else f"{v['name']} ({v['name_as_written']})"
    parts = [name, v["dose"], v["frequency"]]
    s = " ".join(p for p in parts if p)
    return f"{s} for {v['duration']}" if v["duration"] else s


def extract(lines: list[dict], doc_date: str | None = None) -> list[dict]:
    """OCR lines → drug Entities `{kind: "drug", value, text_en, bbox, conf, readable}`."""
    items: list[dict] = []  # {text, cells, generic, written, prefix}
    last_row = -2
    for idx, row in enumerate(group_rows(lines)):
        raw = " ".join(c["text"] for c in row)
        text = normalise(raw)
        prefix = _PREFIX_RE.match(text)
        body = text[prefix.end() :] if prefix else text
        drug = match_drug(body, allow_short=bool(prefix))
        if prefix or drug:
            items.append({"text": body, "cells": list(row), "drug": drug, "prefix": bool(prefix), "raw": raw})
            last_row = idx
        elif items and idx == last_row + 1 and _is_direction(text):
            items[-1]["text"] += " " + text
            items[-1]["raw"] += " " + raw
            items[-1]["cells"] += row
            last_row = idx

    page_garbled = any(_GARBLED_RE.search(it["raw"]) for it in items)
    entities: list[dict] = []
    for it in items:
        conf = round(min(c["conf"] for c in it["cells"]), 3)
        drug = it["drug"]
        readable = drug is not None and conf >= MIN_CONF and not page_garbled
        if readable:
            generic, written, end = drug
            rest = it["text"][end:]
            value = {
                "name": generic, "name_as_written": written, "dose": _dose(rest), "frequency": _frequency(rest),
                "duration": _duration(rest, bare=True), "matched": True, "found_in_documents": True,
            }  # fmt: skip
            label = text_en(value)
        else:  # never pass on a dose or schedule we could not read cleanly
            value = {
                "name": None, "name_as_written": None, "dose": None, "frequency": None, "duration": None,
                "matched": False, "found_in_documents": True, "readable": False,
            }  # fmt: skip
            label = "Medicine: unreadable — see image"
        entities.append({
            "kind": "drug", "value": value, "text_en": label, "conf": conf, "readable": readable,
            "bbox": union_bbox([c["bbox"] for c in it["cells"]]),
        })  # fmt: skip
    return entities
