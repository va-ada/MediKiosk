"""Grounded HPI narrative (`POST /summarize`): Ollama writes ≤ 3 sentences from the given facts only.

Every sentence is checked against the facts; a sentence with a number, clinical word, diagnosis/advice word or a
flipped denial ("fever" when the facts say "No fever") that the facts do not support is dropped and its terms are
reported in `unsupported_terms`. Nothing left (or Ollama down) → the facts' `text_en` joined with "; ".
"""

import json
import logging
import re
from functools import lru_cache
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.extract import ollama_chat
from app.normalize import load_lexicon

log = logging.getLogger("nlp.summarize")

MAX_SENTENCES = 3

SYSTEM_PROMPT = (
    "You write the history of present illness for a doctor from facts a patient reported. "
    "Use ONLY the given facts. Write at most 3 short sentences in plain English, in the third person "
    "(for example 'The patient reports ...'). Copy numbers and units exactly as written in the facts. "
    "Do not add facts, diagnoses or advice."
)
SCHEMA = {
    "type": "object",
    "properties": {"narrative": {"type": "string"}},
    "required": ["narrative"],
    "additionalProperties": False,
}

# Clinical words a narrative may only use if the facts do; plus diagnosis / advice words that never belong in an HPI.
CLINICAL_WORDS = {
    "pain", "ache", "aching", "fever", "swelling", "swollen", "stiffness", "stiff", "injury", "injured", "fall",
    "trauma", "fracture", "sprain", "redness", "warmth", "tenderness", "numbness", "tingling", "weakness", "deformity",
    "locking", "clicking", "cough", "vomiting", "nausea", "diarrhoea", "diarrhea", "rash", "bleeding", "dizziness",
    "headache", "fatigue", "breathlessness", "breathless", "chest", "palpitations", "fainting", "fainted", "weight",
    "allergy", "allergic", "knee", "back", "hip", "shoulder", "hands", "fingers", "ankle", "foot", "neck", "wrist",
    "elbow", "left", "right", "bilateral", "sudden", "gradual", "sharp", "burning", "throbbing", "morning", "night",
    "stairs", "walking", "rest", "medicine", "medicines", "medication", "tablet", "tablets",
    # diagnoses
    "arthritis", "osteoarthritis", "rheumatoid", "gout", "infection", "inflammation", "inflammatory", "effusion",
    "tear", "ligament", "meniscus", "degenerative", "diabetes", "hypertension", "tuberculosis",
    # advice / inference
    "should", "recommend", "recommended", "advise", "advised", "suggest", "suggests", "suggestive", "consult",
    "prescribe", "prescribed", "likely", "probably", "possible", "possibly", "consistent", "diagnosis", "indicates",
}  # fmt: skip
_GENERIC = {"problem", "or", "and", "the", "high", "low", "blood", "folk", "term", "one", "sided", "gall", "kidney"}
SYNONYMS = [
    {"swelling", "swollen", "swell"},
    {"stiffness", "stiff"},
    {"injury", "injured", "fall", "fell", "trauma"},
    {"fainting", "fainted", "faint"},
    {"breathlessness", "breathless", "breathing"},
    {"ache", "aching", "pain", "painful"},
    {"medicine", "medicines", "medication", "tablet", "tablets"},
    {"hands", "hand", "fingers", "finger"},
    {"diarrhoea", "diarrhea"},
]
# "one" is left out on purpose: "one knee", "the right one".
NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "ninety": 90, "hundred": 100,
}  # fmt: skip
NEGATIONS = {"no", "not", "denies", "denied", "without", "nor", "never", "none", "absent", "negative"}
NEG_WINDOW = 3

_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class FactIn(BaseModel):
    section: str
    key: str
    value: Any = None
    text_en: str


class SummarizeIn(BaseModel):
    language: Literal["en"] = "en"
    facts: list[FactIn]


class SummarizeOut(BaseModel):
    narrative: str
    unsupported_terms: list[str]
    fallback_used: bool


# --------------------------------------------------------------------------------------------------------------------
# Faithfulness check
# --------------------------------------------------------------------------------------------------------------------


@lru_cache
def clinical_words() -> frozenset[str]:
    """Small list + single words of the lexicon's concepts (e.g. "constipation", "jaundice")."""
    concept_words = {w for _, concept, _ in load_lexicon().terms for w in re.findall(r"[a-z]+", concept.lower())}
    return frozenset(CLINICAL_WORDS | {w for w in concept_words if len(w) > 3} - _GENERIC)


def _canon(word: str) -> str:
    for group in SYNONYMS:
        if word in group:
            return min(group)
    return word[:-1] if len(word) > 4 and word.endswith("s") else word


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _numbers(words: list[str]) -> set[float]:
    out = set()
    for w in words:
        if w in NUMBER_WORDS:
            out.add(float(NUMBER_WORDS[w]))
        elif w[0].isdigit():
            out.add(float(w))
    return out


def _negated(words: list[str], i: int) -> bool:
    return any(w in NEGATIONS for w in words[max(0, i - NEG_WINDOW) : i])


class Grounding:
    """What the facts support: numbers, words (canonical) and whether a word is only ever mentioned as denied."""

    def __init__(self, facts: list[FactIn]) -> None:
        texts = [f.text_en for f in facts] + [json.dumps(f.value, ensure_ascii=False) for f in facts]
        self.numbers: set[float] = set()
        self.words: set[str] = set()
        affirmed: set[str] = set()
        for text in texts:
            ws = _words(text)
            self.numbers |= _numbers(ws)
            for i, w in enumerate(ws):
                self.words.add(_canon(w))
                if not _negated(ws, i):
                    affirmed.add(_canon(w))
        self.only_denied = self.words - affirmed
        # JSON values: {"value": false} → the slot key is denied, e.g. fever
        for f in facts:
            if isinstance(f.value, dict) and f.value.get("value") is False:
                self.only_denied.add(_canon(f.key))

    def unsupported(self, sentence: str) -> list[str]:
        ws = _words(sentence)
        bad: list[str] = []
        for i, w in enumerate(ws):
            if w in NUMBER_WORDS or w[0].isdigit():
                if not _numbers([w]) <= self.numbers:
                    bad.append(w)
            elif w in clinical_words():
                c = _canon(w)
                if c not in self.words:
                    bad.append(w)
                elif c in self.only_denied and not _negated(ws, i):
                    bad.append(w)  # the facts deny it, the sentence asserts it
        return list(dict.fromkeys(bad))


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text.strip()) if s.strip()]


def ground(narrative: str, facts: list[FactIn]) -> tuple[list[str], list[str]]:
    """(kept sentences, unsupported terms)."""
    g = Grounding(facts)
    kept: list[str] = []
    unsupported: list[str] = []
    for sentence in split_sentences(narrative):
        bad = g.unsupported(sentence)
        if bad:
            log.info("summarize: dropped %r (unsupported: %s)", sentence, bad)
            unsupported += [t for t in bad if t not in unsupported]
        else:
            kept.append(sentence)
    return kept[:MAX_SENTENCES], unsupported


# --------------------------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------------------------


def fallback(facts: list[FactIn]) -> str:
    return "; ".join(f.text_en.strip() for f in facts if f.text_en.strip())


def build_messages(facts: list[FactIn]) -> list[dict[str, str]]:
    lines = "\n".join(f"- {f.text_en}" for f in facts)
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": f"Facts:\n{lines}"}]


async def summarize(req: SummarizeIn) -> SummarizeOut:
    facts = [f for f in req.facts if f.text_en.strip()]
    if not facts:
        return SummarizeOut(narrative="", unsupported_terms=[], fallback_used=True)
    try:
        content = await ollama_chat(build_messages(facts), SCHEMA)
        narrative = str(json.loads(content).get("narrative") or "")
    except (httpx.HTTPError, KeyError, ValueError, AttributeError) as exc:
        log.warning("summarize: Ollama failed: %s", exc)
        return SummarizeOut(narrative=fallback(facts), unsupported_terms=[], fallback_used=True)
    kept, unsupported = ground(narrative, facts)
    if not kept:
        return SummarizeOut(narrative=fallback(facts), unsupported_terms=unsupported, fallback_used=True)
    return SummarizeOut(narrative=" ".join(kept), unsupported_terms=unsupported, fallback_used=False)
