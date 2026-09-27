"""Lab value extraction from OCR lines: rows of "test value unit range" → lab Entities (CONTRACTS §3 labs shape).

Table cells arrive as separate OCR boxes, so boxes are first grouped into visual rows (`document.group_rows`).
A value that doesn't read as a clean number, or a row read with low OCR confidence, becomes `readable: false` —
never a guessed number (CLAUDE.md rule 6).
"""

import re

from app.document import group_rows, union_bbox

MIN_CONF = 0.6

# canonical test name → alias patterns (regex, matched case-insensitively on whole words). Order matters: more
# specific names first (HbA1c before Haemoglobin, LDL/HDL before total cholesterol).
ALIASES: list[tuple[str, list[str]]] = [
    ("HbA1c", [r"hb\s*a1c", r"a1c", r"glyc(?:at|osyl)ed\s+ha?emoglobin"]),
    ("Haemoglobin", [r"ha?emoglobin", r"hgb", r"hb"]),
    ("Fasting glucose", [r"fbs", r"fbg", r"fasting\s+(?:blood\s+|plasma\s+)?(?:sugar|glucose)"]),
    ("Post-prandial glucose", [r"ppbs", r"ppbg", r"post[\s-]*prandial\s+(?:blood\s+|plasma\s+)?(?:sugar|glucose)"]),
    ("TSH", [r"tsh", r"thyroid\s+stimulating\s+hormone"]),
    ("Creatinine", [r"(?:serum\s+|s\.?\s*)?creatinine"]),
    ("LDL cholesterol", [r"ldl(?:[\s-]*c(?:holesterol)?)?"]),
    ("HDL cholesterol", [r"hdl(?:[\s-]*c(?:holesterol)?)?"]),
    ("Total cholesterol", [r"total\s+cholesterol", r"cholesterol(?:\s*,?\s*total)?", r"s\.?\s*cholesterol"]),
    ("Triglycerides", [r"triglycerides?", r"tg"]),
    ("WBC count", [r"(?:total\s+)?wbc(?:\s+count)?", r"tlc", r"total\s+leu[ck]ocyte\s+count", r"white\s+blood\s+cells?"]),
    ("Platelet count", [r"platelets?(?:\s+count)?", r"plt"]),
]  # fmt: skip
_ALIAS_RE = [(name, re.compile(rf"(?<![a-z0-9])(?:{'|'.join(p)})(?![a-z0-9])", re.IGNORECASE)) for name, p in ALIASES]

_NUM = r"\d+(?:,\d{2,3})*(?:\.\d+)?"
# A standalone number: not glued to letters/dates/exponents ("HbA1c", "12/08/2026", "x10^3" are not values).
_VALUE_RE = re.compile(rf"(?<![\w.^/,\-])({_NUM})(?![\d/^]|[.,\-]\d)")
# Something where the value should be that is not a clean number: OCR digit/letter confusions like "1O.2", "l0".
_GARBLED_RE = re.compile(r"(?<![\w.])(?=[\dOoIl.,]*\d)(?=[\dOoIl.,]*[OoIl])[\dOoIl.,]{2,}(?![\w.])")
_DASH = r"(?:-|–|—|to)"
_RANGE_RES: list[tuple[str, re.Pattern[str]]] = [
    ("between", re.compile(rf"\(?\s*({_NUM})\s*{_DASH}\s*({_NUM})\s*\)?", re.IGNORECASE)),
    ("below", re.compile(rf"\(?\s*(?:<=?|≤|up\s*to|upto|less\s+than)\s*({_NUM})\s*\)?", re.IGNORECASE)),
    ("above", re.compile(rf"\(?\s*(?:>=?|≥|more\s+than|greater\s+than)\s*({_NUM})\s*\)?", re.IGNORECASE)),
]
_UNIT_RE = re.compile(r"^(?:%|[\w×µμ^.]*[/^][\w×µμ^/.]*|fl|pg|ratio|sec|seconds|mmhg)$", re.IGNORECASE)


def _num(s: str) -> float | int:
    s = s.replace(",", "")
    return float(s) if "." in s else int(s)


def _canonical(name_part: str) -> str | None:
    for name, rx in _ALIAS_RE:
        if rx.search(name_part):
            return name
    return None


def _range_text(kind: str, lo: str | None, hi: str | None) -> str:
    return {"between": f"{lo}–{hi}", "below": f"< {hi}", "above": f"> {lo}"}[kind]


def parse_row(text: str) -> dict | None:
    """Parse one row's text → {test, value, unit, ref_low, ref_high, flag, value_text, range_text, garbled}.

    Returns None when the row is not a lab result (header, address, date line, prose)."""
    text = " ".join(text.split())
    m = _VALUE_RE.search(text)
    g = _GARBLED_RE.search(text)
    garbled = False
    if g and (not m or g.start() <= m.start()):  # the first number-like token is not a clean number
        name_part, rest, value_text, garbled = text[: g.start()], text[g.end() :], g.group(0), True
    elif m:
        name_part, rest, value_text = text[: m.start()], text[m.end() :], m.group(1)
    else:
        return None
    name_part = name_part.strip(" :-=|")
    if len(re.findall(r"[A-Za-z]", name_part)) < 2:
        return None
    test = _canonical(name_part)

    kind = lo = hi = None
    unit_text = rest
    for k, rx in _RANGE_RES:
        if r := rx.search(rest):
            kind = k
            lo, hi = (
                (r.group(1), r.group(2))
                if k == "between"
                else (None, r.group(1))
                if k == "below"
                else (r.group(1), None)
            )
            unit_text = rest[: r.start()]
            break
    unit_tokens = unit_text.replace("(", " ").replace(")", " ").split()
    if kind:
        unit = " ".join(unit_tokens) or None
    else:
        unit = unit_tokens[0] if unit_tokens and _UNIT_RE.match(unit_tokens[0]) else None

    if test is None:
        # Unknown test name: accept only a clean table row (name, unit AND reference range; no "Label:" lines).
        if ":" in name_part or not unit or not kind or len(name_part) > 40:
            return None
        test = name_part
    if unit and len(unit) > 15:  # prose after the number, not a unit
        return None

    ref_low = _num(lo) if lo else None
    ref_high = _num(hi) if hi else None
    value = None if garbled else _num(value_text)
    flag = "unknown"
    if value is not None and kind:
        if ref_low is not None and value < ref_low:
            flag = "low"
        elif ref_high is not None and value > ref_high:
            flag = "high"
        else:
            flag = "normal"
    return {
        "test": test, "value": value, "unit": unit, "ref_low": ref_low, "ref_high": ref_high, "flag": flag,
        "value_text": value_text, "range_text": _range_text(kind, lo, hi) if kind else None, "garbled": garbled,
    }  # fmt: skip


def text_en(p: dict) -> str:
    parts = [p["test"], p["value_text"]]
    if p["unit"]:
        parts.append(p["unit"])
    if p["range_text"]:
        parts.append(f"(ref {p['range_text']})")
    if p["flag"] in ("low", "high"):
        parts.append(p["flag"].upper())
    return " ".join(parts)


def extract(lines: list[dict], doc_date: str | None = None) -> list[dict]:
    """OCR lines → lab Entities `{kind: "lab", value, text_en, bbox, conf, readable}`."""
    entities: list[dict] = []
    for row in group_rows(lines):
        p = parse_row(" ".join(c["text"] for c in row))
        if p is None:
            continue
        conf = round(min(c["conf"] for c in row), 3)
        readable = conf >= MIN_CONF and not p["garbled"]
        value = {k: p[k] for k in ("test", "value", "unit", "ref_low", "ref_high", "flag")} | {"date": doc_date}
        if not readable:  # never pass on a number we could not read cleanly
            value |= {"value": None, "flag": "unknown", "readable": False}
        entities.append({
            "kind": "lab", "value": value, "conf": conf, "readable": readable,
            "text_en": text_en(p) if readable else f"{p['test']}: unreadable — see image",
            "bbox": union_bbox([c["bbox"] for c in row]),
        })  # fmt: skip
    return entities
