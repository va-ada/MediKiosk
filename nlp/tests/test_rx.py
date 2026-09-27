import pytest

from app import document, rx
from app.config import settings
from tests import test_document


def L(text: str, y: int = 100, conf: float = 0.95) -> dict:
    return {"text": text, "bbox": [100, y, 20 * len(text), 30], "conf": conf}


def one(*lines: dict) -> dict:
    ents = rx.extract(list(lines))
    assert len(ents) == 1, ents
    return ents[0]


# ------------------------------------------------------------------ the §3 drugs shape


def test_metformin_line() -> None:
    e = one(L("Tab Metformin 500 mg BD x 30 days"))
    assert e["kind"] == "drug" and e["readable"] is True and e["conf"] == 0.95
    assert e["value"] == {"name": "Metformin", "name_as_written": "Metformin", "dose": "500 mg",
                          "frequency": "twice daily", "duration": "30 days", "matched": True,
                          "found_in_documents": True}  # fmt: skip
    assert e["text_en"] == "Metformin 500 mg twice daily for 30 days"
    assert e["bbox"] == [100, 100, 20 * 33, 30]


@pytest.mark.parametrize(
    ("code", "meaning"),
    [
        ("OD", "once daily"), ("BD", "twice daily"), ("TDS", "three times daily"), ("QID", "four times daily"),
        ("HS", "at bedtime"), ("SOS", "when needed"), ("AC", "before food"), ("PC", "after food"),
        ("od", "once daily"), ("Sos", "when needed"),
    ],
)  # fmt: skip
def test_frequency_codes(code: str, meaning: str) -> None:
    assert one(L(f"Tab Paracetamol 650 mg {code}"))["value"]["frequency"] == meaning


@pytest.mark.parametrize(
    ("text", "freq"),
    [
        ("Tab Metformin 500 mg 1-0-1", "twice daily"),
        ("Tab Metformin 500 mg 1-1-1", "three times daily"),
        ("Tab Amlodipine 5 mg 0-0-1", "once daily"),
        ("Yograj Guggulu 2 tab BD after food", "twice daily, after food"),
        ("Tab Pantoprazole 40 mg OD before breakfast", "once daily, before food"),
        ("Tab Amlodipine 5 mg once daily at night", "once daily, at bedtime"),
        ("Tab Metformin 500 mg", None),
    ],
)
def test_frequency_phrases(text: str, freq: str | None) -> None:
    assert one(L(text))["value"]["frequency"] == freq


@pytest.mark.parametrize(
    ("text", "duration"),
    [
        ("Tab Amoxicillin 500 mg TDS x 5 days", "5 days"),
        ("Tab Amoxicillin 500 mg TDS x5d", "5 days"),
        ("Tab Amoxicillin 500 mg TDS × 7 days", "7 days"),
        ("Tab Metformin 500 mg BD for 1 month", "1 month"),
        ("Tab Metformin 500 mg BD for 3 months", "3 months"),
        ("Cap Amoxicillin 250 mg TDS x 1 week", "1 week"),
        ("Tab Amlodipine 5 mg OD", None),
    ],
)
def test_duration(text: str, duration: str | None) -> None:
    assert one(L(text))["value"]["duration"] == duration


@pytest.mark.parametrize(
    ("text", "dose"),
    [
        ("Tab Metformin 500 mg BD", "500 mg"),
        ("Tab Metformin 500mg BD", "500 mg"),
        ("Syp Paracetamol 5 ml TDS", "5 ml"),
        ("Tab Metformin 0.5 g BD", "0.5 g"),
        ("Dashmool Kwath 20 ml BD", "20 ml"),
        ("Yograj Guggulu 2 tab BD", "2 tab"),
        ("Tab Metformin BD", None),
    ],
)
def test_dose(text: str, dose: str | None) -> None:
    assert one(L(text))["value"]["dose"] == dose


# ------------------------------------------------------------------ recognising medicine lines


@pytest.mark.parametrize(
    ("text", "name", "written"),
    [
        ("Tab. Metformin 500 mg", "Metformin", "Metformin"),
        ("1. Tab Amlodipine 5 mg OD", "Amlodipine", "Amlodipine"),
        ("Cap Amoxicillin 500 mg", "Amoxicillin", "Amoxicillin"),
        ("Tab Glycomet 500 mg BD", "Metformin", "Glycomet"),  # brand → generic
        ("Tab Dolo 650 SOS", "Paracetamol", "Dolo 650"),  # brand containing a number
        ("Tab Pan 40 mg OD", "Pantoprazole", "Pan"),  # short brand, exact match
        ("Metformn 500 mg BD", "Metformin", "Metformn"),  # no prefix, fuzzy ≥ 85
        ("Yograj Guggulu 2 tab BD", "Yograj guggulu", "Yograj Guggulu"),
        ("TabMetformin500mgBDx30days", "Metformin", "Metformin"),  # glued OCR from a phone photo
    ],
)
def test_drug_names(text: str, name: str, written: str) -> None:
    v = one(L(text))["value"]
    assert (v["name"], v["name_as_written"], v["matched"]) == (name, written, True)


def test_glued_photo_line_fully_parsed() -> None:
    v = one(L("TabParacetamol 650 mgSOS"))["value"]
    assert (v["dose"], v["frequency"]) == ("650 mg", "when needed")


def test_brand_shown_in_text() -> None:
    assert one(L("Tab Glycomet 500 mg BD"))["text_en"] == "Metformin (Glycomet) 500 mg twice daily"


@pytest.mark.parametrize(
    "text",
    [
        "Rx",
        "Diagnosis: Type 2 diabetes mellitus, Hypertension",
        "Advice: low-salt diet, walk 30 minutes daily.",
        "Review after 1 month with FBS report.",
        "Patient: Kamla Devi",
        "Pan card number",  # short brands ("Pan") only count after Tab/Cap/Syp/Inj
    ],
)
def test_non_drug_lines_ignored(text: str) -> None:
    assert rx.extract([L(text)]) == []


# ------------------------------------------------------------------ never guessed


def test_prefix_without_known_drug_unreadable() -> None:
    e = one(L("Tab Xyzzol 10 mg OD"))
    assert e["readable"] is False and e["text_en"] == "Medicine: unreadable — see image"
    assert e["value"] == {"name": None, "name_as_written": None, "dose": None, "frequency": None, "duration": None,
                          "matched": False, "found_in_documents": True, "readable": False}  # fmt: skip


def test_low_conf_unreadable() -> None:
    e = one(L("Tab Metformin 500 mg BD", conf=0.5))
    assert e["readable"] is False and e["conf"] == 0.5 and e["value"]["dose"] is None


def test_garbled_digits_make_whole_page_unreadable() -> None:
    ents = rx.extract([L("Tab Pantoprazole 4o mg OD", y=100), L("Tab Metformin 500 mg BD", y=200)])
    assert [e["readable"] for e in ents] == [False, False]
    assert all(e["value"]["dose"] is None for e in ents)


def test_direction_row_continues_medicine_above() -> None:
    e = one(L("Tab Pantoprazole 40 mg OD", y=100), L("before breakfast x 14 days", y=150))
    assert e["value"]["frequency"] == "once daily, before food" and e["value"]["duration"] == "14 days"
    assert e["bbox"] == [100, 100, 20 * 26, 80]


def test_labelled_row_is_not_a_continuation() -> None:
    e = one(L("Tab Metformin 500 mg BD", y=100), L("Follow-up: Medicine OPD after 7 days.", y=150))
    assert e["value"]["duration"] is None


def test_drug_aliases_loaded_from_csv() -> None:
    aliases = {a for a, _, _ in rx.drug_aliases()}
    assert {"metformin", "glycomet", "dolo 650", "yograj guggulu"} <= aliases


# ------------------------------------------------------------------ real samples

real_engine = test_document.real_engine  # one shared RapidOCR instance per test session


def _drugs_of(name: str, ocr: document.OcrEngine) -> list[dict]:
    path = settings.content_dir / "samples" / name
    if not path.exists():
        pytest.skip(f"sample {path} missing")
    return [e.model_dump() for e in document.process(path.read_bytes(), ocr).entities if e.kind == "drug"]


@pytest.mark.parametrize("name", ["rx_allopathic.png", "rx_allopathic_photo.png"])
def test_rx_allopathic_sample(real_engine: document.OcrEngine, name: str) -> None:
    got = [(d["value"]["name"], d["value"]["dose"], d["value"]["frequency"], d["value"]["duration"], d["readable"])
           for d in _drugs_of(name, real_engine)]  # fmt: skip
    assert got == [
        ("Metformin", "500 mg", "twice daily", "30 days", True),
        ("Amlodipine", "5 mg", "once daily", None, True),
    ]


def test_rx_ayurveda_sample(real_engine: document.OcrEngine) -> None:
    got = [d["text_en"] for d in _drugs_of("rx_ayurveda.png", real_engine)]
    assert got == ["Yograj guggulu 2 tab twice daily, after food", "Dashmool kwath 20 ml twice daily"]


def test_discharge_summary_medicines(real_engine: document.OcrEngine) -> None:
    got = [d["text_en"] for d in _drugs_of("discharge_summary.png", real_engine)]
    assert got == [
        "Amoxicillin 500 mg three times daily for 5 days",
        "Paracetamol 650 mg when needed",
        "Metformin 500 mg twice daily",
    ]


def test_handwritten_sample_not_guessed(real_engine: document.OcrEngine) -> None:
    drugs = _drugs_of("handwritten_style.png", real_engine)
    assert drugs, "the medicine lines should still be flagged (with bbox) so the doctor can open the image"
    for d in drugs:
        assert d["readable"] is False and d["value"]["dose"] is None and d["value"]["name"] is None
        assert d["bbox"] is not None


def test_lab_report_has_no_drugs(real_engine: document.OcrEngine) -> None:
    assert _drugs_of("lab_report_cbc.png", real_engine) == []
