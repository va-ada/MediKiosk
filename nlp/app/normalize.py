"""Normalisation: folk terms → concepts and time phrases → days, from `content/lexicon_hi.yaml` + `festivals.yaml`.

Pure rules, no model. Used by `/extract` to fill `duration_days` when the model leaves it null.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from app.config import settings

UNIT_DAYS: dict[str, int] = {"day": 1, "week": 7, "month": 30, "year": 365}

# Optional words next to a duration ("teen mahine se", "for 3 weeks", "since 2 days"); they join the phrase.
_BEFORE = {"for", "since", "past", "last", "pichhle", "pichle", "पिछले"}
_AFTER = {"se", "से", "sey", "ago", "pehle", "पहले"}

# Relative phrases → days ago. Matched as whole token sequences.
RELATIVE: dict[tuple[str, ...], int] = {
    ("कल",): 1,
    ("kal",): 1,
    ("yesterday",): 1,
    ("परसों",): 2,
    ("parson",): 2,
    ("parso",): 2,
    ("day", "before", "yesterday"): 2,
    **{(p, w): 7 for p in ("पिछले", "pichhle", "pichle") for w in ("हफ्ते", "हफ़्ते", "hafte")},
    **{(p, w): 30 for p in ("पिछले", "pichhle", "pichle") for w in ("महीने", "महिने", "mahine")},
    **{(p, w): 365 for p in ("पिछले", "pichhle", "pichle") for w in ("साल", "saal", "sal")},
    ("last", "week"): 7,
    ("last", "month"): 30,
    ("last", "year"): 365,
}

# Festival names as spoken → key in festivals.yaml; the phrase needs a "since/after" word next to it.
FESTIVAL_NAMES: dict[str, str] = {
    "diwali": "diwali",
    "deepawali": "diwali",
    "दिवाली": "diwali",
    "दीवाली": "diwali",
    "दीपावली": "diwali",
    "holi": "holi",
    "होली": "holi",
}
_FESTIVAL_AFTER = [("ke", "baad"), ("के", "बाद"), ("se",), ("से",)]
_FESTIVAL_BEFORE = [("since",), ("after",)]

# Digits (Latin or Devanagari, optional decimal), Latin words, Devanagari words (letters + vowel signs, no danda).
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[A-Za-z']+|[ऀ-ॣॱ-ॿ]+")


@dataclass(frozen=True)
class Token:
    text: str  # NFC + lower-case, for matching
    start: int
    end: int


@dataclass(frozen=True)
class Lexicon:
    terms: list[tuple[tuple[str, ...], str, bool]]  # (tokenised match, concept, ambiguous), longest first
    negation_cues: list[tuple[str, ...]]
    numbers: dict[str, float]
    units: dict[str, str]  # word → unit key (day/week/month/year)
    festivals: dict[str, dict[int, date]]  # key → {year: date}; null dates are left out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def tokenize(text: str) -> list[Token]:
    """Tokens of NFC text (offsets refer to the NFC string returned by `_clean`)."""
    return [Token(m.group().lower(), m.start(), m.end()) for m in _TOKEN.finditer(text)]


def _words(phrase: str) -> tuple[str, ...]:
    return tuple(t.text for t in tokenize(_clean(phrase)))


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache
def load_lexicon(content_dir: Path | None = None) -> Lexicon:
    content = Path(content_dir or settings.content_dir)
    lex = _read_yaml(content / "lexicon_hi.yaml")
    terms = [
        (_words(m), str(t["concept"]), bool(t.get("ambiguous", False)))
        for t in lex.get("terms", [])
        for m in t.get("match", [])
        if _words(m)
    ]
    terms.sort(key=lambda t: -len(t[0]))
    festivals: dict[str, dict[int, date]] = {}
    for key, years in (_read_yaml(content / "festivals.yaml") or {}).items():
        dated = {int(y): date.fromisoformat(str(d)) for y, d in (years or {}).items() if d}
        festivals[str(key)] = dated
    return Lexicon(
        terms=terms,
        negation_cues=sorted({w for c in lex.get("negation_cues", []) if (w := _words(c))}, key=lambda c: -len(c)),
        numbers={_clean(str(k)).lower(): float(v) for k, v in (lex.get("numbers") or {}).items()},
        units={_clean(w).lower(): unit for unit, words in (lex.get("units") or {}).items() for w in words},
        festivals=festivals,
    )


def _number(word: str, lex: Lexicon) -> float | None:
    if word in lex.numbers:
        return lex.numbers[word]
    try:
        return float(word)  # also Devanagari digits (३ → 3.0)
    except ValueError:
        return None


def to_days(value: float) -> int:
    """Round half up (1.5 months = 45 days, 2.5 weeks = 18 days)."""
    return int(value + 0.5)


def _match_at(tokens: list[Token], i: int, seq: tuple[str, ...]) -> bool:
    return tuple(t.text for t in tokens[i : i + len(seq)]) == seq


def _durations(text: str, tokens: list[Token], lex: Lexicon, today: date) -> list[dict[str, Any]]:
    found: list[tuple[int, int, int]] = []  # (first token, last token exclusive, days)
    used = [False] * len(tokens)

    def claim(a: int, b: int, days: int) -> None:
        found.append((a, b, days))
        for k in range(a, b):
            used[k] = True

    # 1. number + unit ("teen mahine", "3 weeks", "डेढ़ साल")
    for i in range(len(tokens) - 1):
        n, unit = _number(tokens[i].text, lex), lex.units.get(tokens[i + 1].text)
        if n is None or unit is None or used[i] or used[i + 1]:
            continue
        a, b = i, i + 2
        if a > 0 and tokens[a - 1].text in _BEFORE:
            a -= 1
        if b < len(tokens) and tokens[b].text in _AFTER:
            b += 1
        claim(a, b, to_days(n * UNIT_DAYS[unit]))

    # 2. relative phrases ("kal se", "पिछले हफ्ते"), longest first
    for seq, days in sorted(RELATIVE.items(), key=lambda kv: -len(kv[0])):
        for i in range(len(tokens) - len(seq) + 1):
            if not any(used[i : i + len(seq)]) and _match_at(tokens, i, seq):
                b = i + len(seq)
                if b < len(tokens) and tokens[b].text in _AFTER:
                    b += 1
                claim(i, b, days)

    # 3. festivals ("Diwali ke baad", "since Holi") — only when festivals.yaml has a date on or before today
    for i, tok in enumerate(tokens):
        key = FESTIVAL_NAMES.get(tok.text)
        if key is None or used[i]:
            continue
        a, b = i, i + 1
        after = next((s for s in _FESTIVAL_AFTER if _match_at(tokens, b, s)), None)
        before = next((s for s in _FESTIVAL_BEFORE if i >= len(s) and _match_at(tokens, i - len(s), s)), None)
        if after is None and before is None:
            continue
        past = [d for d in lex.festivals.get(key, {}).values() if d <= today]
        if not past:
            continue  # date not in festivals.yaml (never guessed)
        a -= len(before or ())
        b += len(after or ())
        claim(a, b, (today - max(past)).days)

    found.sort()
    return [{"phrase": text[tokens[a].start : tokens[b - 1].end], "days": days} for a, b, days in found]


def _terms(text: str, tokens: list[Token], lex: Lexicon) -> list[dict[str, Any]]:
    out: list[tuple[int, dict[str, Any]]] = []
    used = [False] * len(tokens)
    for seq, concept, ambiguous in lex.terms:  # longest first, so "high bp" wins over "bp"
        for i in range(len(tokens) - len(seq) + 1):
            if not any(used[i : i + len(seq)]) and _match_at(tokens, i, seq):
                for k in range(i, i + len(seq)):
                    used[k] = True
                phrase = text[tokens[i].start : tokens[i + len(seq) - 1].end]
                out.append((i, {"phrase": phrase, "concept": concept, "ambiguous": ambiguous}))
    return [t for _, t in sorted(out, key=lambda x: x[0])]


def normalize(text: str, language: str, today: date | None = None) -> dict[str, Any]:
    """`{"text", "durations":[{"phrase","days"}], "terms":[{"phrase","concept","ambiguous"}]}`.

    `text` is the cleaned input (NFC, single spaces); phrases are substrings of it. `language` is accepted for the
    API shape — Hindi, romanised Hindi and English are all matched regardless (patients mix them).
    """
    del language
    clean = _clean(text)
    tokens = tokenize(clean)
    lex = load_lexicon()
    return {
        "text": clean,
        "durations": _durations(clean, tokens, lex, today or datetime.now(ZoneInfo("Asia/Kolkata")).date()),
        "terms": _terms(clean, tokens, lex),
    }
