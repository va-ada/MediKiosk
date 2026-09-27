import pytest

from app.asr import confidence


@pytest.mark.parametrize(
    ("text", "duration", "lang", "expected"),
    [
        ("", 2.0, "hi", 0.0),  # empty
        ("   ", 2.0, "en", 0.0),  # whitespace only
        ("मेरे घुटने में दर्द है", 2.0, "hi", 0.85),  # 5 words / 2 s, Devanagari
        ("my knee hurts", 1.5, "en", 0.85),  # 3 words / 1.5 s, Latin
        ("my knee hurts", 1.5, "hi", 0.4),  # wrong script for hi
        ("मेरे घुटने में दर्द है", 2.0, "en", 0.4),  # wrong script for en
        ("123 456", 2.0, "en", 0.4),  # no letters at all
        ("दर्द", 5.0, "hi", 0.4),  # too slow: 0.2 words/s
        ("एक दो तीन चार पाँच छह सात आठ नौ दस दस", 2.0, "hi", 0.4),  # too fast: 5.5 words/s
        ("दर्द", 2.0, "hi", 0.85),  # boundary 0.5 words/s is fine
        ("a b c d e", 1.0, "en", 0.85),  # boundary 5 words/s is fine
        ("pain", 0.0, "en", 0.4),  # zero duration
        ("pain", 1.0, "ta", 0.4),  # unsupported language
    ],
)
def test_confidence(text: str, duration: float, lang: str, expected: float) -> None:
    assert confidence(text, duration, lang) == expected
