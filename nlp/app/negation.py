"""Negation double-check: a model `true` next to a denial ("bukhar nahi hai") is not trusted.

Rule: for every slot the model set to `true`, if a negation cue (lexicon `negation_cues`) is within 3 tokens of any
keyword for that slot, the slot becomes null, a note is added and the answer is `uncertain` (the patient is asked
again / taps). Deliberately conservative: a false alarm only costs one tap, a wrong "yes" becomes a wrong fact.
"""

import unicodedata
from typing import Any

from app.normalize import load_lexicon, tokenize

WINDOW = 3  # tokens between a cue and a keyword

# slot → keywords (Hindi, romanised Hindi, English); multi-word keywords are token sequences.
DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "fever": ["बुखार", "ताप", "bukhar", "bukhaar", "buqhar", "taap", "fever", "temperature"],
    "swelling": ["सूजन", "सूजा", "सूजी", "sujan", "soojan", "sujaan", "suja", "sooja", "swelling", "swollen"],
    "injury": ["चोट", "गिरा", "गिरी", "chot", "gira", "giri", "injury", "injured", "fell", "fall"],
    "chest_pain": ["सीने", "सीना", "छाती", "seene", "sine", "seena", "chhati", "chati", "chest"],
    "breathless": ["साँस", "सांस", "saans", "sans", "saas", "breath", "breathe", "breathing", "breathless"],
    "fainted": ["बेहोश", "behosh", "behoshi", "faint", "fainted", "unconscious", "passed out"],
}


def _find(tokens: list[str], seq: tuple[str, ...]) -> list[tuple[int, int]]:
    """(start, end-inclusive) token spans where `seq` occurs."""
    n = len(seq)
    return [(i, i + n - 1) for i in range(len(tokens) - n + 1) if tuple(tokens[i : i + n]) == seq]


def _seq(phrase: str) -> tuple[str, ...]:
    return tuple(t.text for t in tokenize(unicodedata.normalize("NFC", phrase)))


def check(
    text: str, slots: dict[str, Any], slot_keywords: dict[str, list[str]] | None = None
) -> tuple[dict[str, Any], list[str], bool]:
    """Returns (slots, notes, uncertain). `slots` is a new dict; the input is not changed."""
    keywords = DEFAULT_KEYWORDS if slot_keywords is None else slot_keywords
    tokens = [t.text for t in tokenize(unicodedata.normalize("NFC", text))]
    cues = [(c, span) for cue in load_lexicon().negation_cues for span in _find(tokens, cue) for c in [" ".join(cue)]]
    out, notes, uncertain = dict(slots), [], False
    for name, value in slots.items():
        if value is not True or name not in keywords:
            continue
        hit = next(
            (
                (cue, " ".join(tokens[ks : ke + 1]))
                for kw in keywords[name]
                if (seq := _seq(kw))
                for ks, ke in _find(tokens, seq)
                for cue, (cs, ce) in cues
                if cs <= ke + WINDOW and ce >= ks - WINDOW
            ),
            None,
        )
        if hit:
            out[name] = None
            notes.append(f"{name}=true dropped: negation '{hit[0]}' near '{hit[1]}'")
            uncertain = True
    return out, notes, uncertain
