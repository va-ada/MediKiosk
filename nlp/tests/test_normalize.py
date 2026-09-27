import shutil
from datetime import date
from pathlib import Path

import pytest

from app import normalize as norm
from app.config import settings
from app.normalize import normalize

TODAY = date(2026, 11, 20)


def days(text: str, language: str = "hi") -> list[int]:
    return [d["days"] for d in normalize(text, language, today=TODAY)["durations"]]


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        # Hindi (Devanagari)
        ("तीन महीने से घुटने में दर्द है", "hi", [90]),
        ("दो हफ्ते से सूजन है", "hi", [14]),
        ("डेढ़ महीने से", "hi", [45]),  # 1.5 months → 45 days
        ("ढाई साल से कमर दर्द", "hi", [913]),  # 2.5 × 365 = 912.5 → rounds half up
        ("कल से बुखार है", "hi", [1]),
        ("परसों से दर्द है", "hi", [2]),
        ("पिछले हफ्ते गिर गया था", "hi", [7]),
        ("पिछले महीने से", "hi", [30]),
        ("५ दिन से", "hi", [5]),  # Devanagari digits
        # Romanised Hindi
        ("teen mahine se ghutne mein dard hai", "hi", [90]),
        ("ek hafte se", "hi", [7]),
        ("dedh saal se", "hi", [548]),
        ("kal se bukhar hai", "hi", [1]),
        ("pichhle hafte se sujan hai", "hi", [7]),
        ("pichhle do hafte se", "hi", [14]),
        # English
        ("for 3 weeks", "en", [21]),
        ("since two months", "en", [60]),
        ("my knee hurts for 1.5 years", "en", [548]),
        ("it started last week", "en", [7]),
        ("ten days ago", "en", [10]),
        # Mixed
        ("3 mahine se knee pain", "hi", [90]),
        ("knee में 2 हफ्ते से दर्द", "hi", [14]),
        ("do din pehle gir gaya, aur 3 weeks se sujan", "hi", [2, 21]),
        # Nothing to find
        ("घुटने में दर्द है", "hi", []),
        ("mahine se dard hai", "hi", []),  # unit without a number
        ("do you have pain", "en", []),  # "do" without a unit
    ],
)
def test_durations(text: str, language: str, expected: list[int]) -> None:
    assert days(text, language) == expected


def test_duration_phrase_is_substring() -> None:
    out = normalize("  teen   mahine se ghutne mein dard hai ", "hi", today=TODAY)
    assert out["text"] == "teen mahine se ghutne mein dard hai"
    assert out["durations"] == [{"phrase": "teen mahine se", "days": 90}]


def test_terms_hindi_and_romanised() -> None:
    out = normalize("मुझे शुगर है और ghutne mein dard hai, bukhar nahi", "hi", today=TODAY)
    assert [(t["phrase"], t["concept"]) for t in out["terms"]] == [
        ("शुगर", "diabetes"),
        ("ghutne mein dard", "knee pain"),
        ("bukhar", "fever"),
    ]


def test_terms_longest_match_and_ambiguity() -> None:
    terms = normalize("High BP hai, aur kabhi kabhi bp low", "hi", today=TODAY)["terms"]
    assert terms[0] == {"phrase": "High BP", "concept": "high blood pressure", "ambiguous": False}
    assert terms[1] == {"phrase": "bp", "concept": "blood pressure problem", "ambiguous": True}


def test_terms_whole_words_only() -> None:
    assert normalize("gastric problem", "en", today=TODAY)["terms"] == []  # "gas" must not match inside "gastric"


def test_festival_without_date_yields_nothing() -> None:
    # festivals.yaml ships with null dates: festival phrases must be ignored, never guessed.
    out = normalize("Diwali ke baad se dard hai", "hi", today=TODAY)
    assert out["durations"] == []
    assert normalize("होली के बाद से", "hi", today=TODAY)["durations"] == []


@pytest.fixture
def dated_festivals(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(settings.content_dir / "lexicon_hi.yaml", tmp_path / "lexicon_hi.yaml")
    # Test-only dates (not real calendar dates).
    (tmp_path / "festivals.yaml").write_text(
        'diwali:\n  2025: "2025-10-21"\n  2026: "2026-11-08"\nholi:\n  2026: null\n'
    )
    real = norm.load_lexicon
    monkeypatch.setattr(norm, "load_lexicon", lambda: real(tmp_path))


def test_festival_with_date(dated_festivals: None) -> None:
    assert normalize("Diwali ke baad se ghutna dukh raha hai", "hi", today=TODAY)["durations"] == [
        {"phrase": "Diwali ke baad", "days": 12}
    ]
    assert days("दिवाली के बाद से") == [12]
    assert days("since Diwali") == [12]
    assert days("Diwali ke baad", "hi") == [12]
    # before this year's Diwali → the previous year's date is used
    assert [d["days"] for d in normalize("since diwali", "en", today=date(2026, 3, 1))["durations"]] == [131]
    assert days("Holi ke baad") == []  # still null
    assert days("Diwali par mithai khayi") == []  # name alone is not a time phrase
