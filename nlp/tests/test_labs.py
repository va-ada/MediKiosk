import pytest

from app import document, labs
from app.config import settings
from tests import test_document


def row(*cells: str, y: int = 100, conf: float = 0.99) -> list[dict]:
    """One table row as separate OCR boxes, left to right."""
    out, x = [], 50
    for c in cells:
        out.append({"text": c, "bbox": [x, y, 15 * len(c), 30], "conf": conf})
        x += 15 * len(c) + 60
    return out


def one(lines: list[dict], doc_date: str | None = None) -> dict:
    ents = labs.extract(lines, doc_date=doc_date)
    assert len(ents) == 1, ents
    return ents[0]


# ------------------------------------------------------------------ ranges


@pytest.mark.parametrize(
    ("ref", "lo", "hi", "range_text"),
    [
        ("12.0 - 15.0", 12.0, 15.0, "12.0–15.0"),
        ("12.0–15.0", 12.0, 15.0, "12.0–15.0"),
        ("12.0-15.0", 12.0, 15.0, "12.0–15.0"),
        ("(12-15)", 12, 15, "12–15"),
        ("12 to 15", 12, 15, "12–15"),
    ],
)
def test_between_ranges(ref: str, lo: float, hi: float, range_text: str) -> None:
    e = one(row("Haemoglobin", "10.2", "g/dL", ref), doc_date="2026-08-12")
    assert e["kind"] == "lab" and e["readable"] is True
    assert e["value"] == {"test": "Haemoglobin", "value": 10.2, "unit": "g/dL", "ref_low": lo, "ref_high": hi,
                          "flag": "low", "date": "2026-08-12"}  # fmt: skip
    assert e["text_en"] == f"Haemoglobin 10.2 g/dL (ref {range_text}) LOW"


def test_upper_limit_only() -> None:
    e = one(row("HbA1c", "7.4", "%", "< 5.7"))
    assert e["value"]["ref_low"] is None and e["value"]["ref_high"] == 5.7 and e["value"]["flag"] == "high"
    assert e["text_en"] == "HbA1c 7.4 % (ref < 5.7) HIGH"
    assert one(row("HbA1c", "5.2", "%", "<5.7"))["value"]["flag"] == "normal"


def test_lower_limit_only() -> None:
    e = one(row("HDL", "35", "mg/dL", "> 40"))
    assert e["value"]["test"] == "HDL cholesterol" and e["value"]["ref_low"] == 40 and e["value"]["flag"] == "low"


def test_flags() -> None:
    assert one(row("Hb", "13.1", "g/dL", "12.0-15.0"))["value"]["flag"] == "normal"
    assert one(row("Hb", "16", "g/dL", "12.0-15.0"))["value"]["flag"] == "high"
    e = one(row("Hb", "13.1", "g/dL"))  # no range parsed → unknown, never guessed
    assert e["value"]["flag"] == "unknown" and e["value"]["ref_low"] is None
    assert e["text_en"] == "Haemoglobin 13.1 g/dL"


def test_normal_has_no_flag_word() -> None:
    assert one(row("TSH", "2.1", "uIU/mL", "0.4-4.0"))["text_en"] == "TSH 2.1 uIU/mL (ref 0.4–4.0)"


# ------------------------------------------------------------------ names


@pytest.mark.parametrize(
    ("written", "canonical"),
    [
        ("Hb", "Haemoglobin"), ("HGB", "Haemoglobin"), ("Hemoglobin", "Haemoglobin"), ("Haemoglobin", "Haemoglobin"),
        ("FBS", "Fasting glucose"), ("Fasting Blood Sugar", "Fasting glucose"), ("Fasting glucose", "Fasting glucose"),
        ("HbA1c", "HbA1c"), ("Hb A1c", "HbA1c"), ("Glycated haemoglobin", "HbA1c"),
        ("TSH", "TSH"), ("Serum Creatinine", "Creatinine"), ("S. Creatinine", "Creatinine"),
        ("Total Cholesterol", "Total cholesterol"), ("Cholesterol, Total", "Total cholesterol"),
        ("LDL Cholesterol", "LDL cholesterol"), ("LDL-C", "LDL cholesterol"), ("HDL", "HDL cholesterol"),
        ("Triglycerides", "Triglycerides"), ("Total WBC count", "WBC count"), ("TLC", "WBC count"),
        ("WBC", "WBC count"), ("Platelets", "Platelet count"), ("Platelet count", "Platelet count"),
    ],
)  # fmt: skip
def test_name_aliases(written: str, canonical: str) -> None:
    assert one(row(written, "5.0", "mg/dL", "1-10"))["value"]["test"] == canonical


def test_unknown_test_needs_unit_and_range() -> None:
    assert one(row("MCV", "79", "fL", "83-101"))["value"]["test"] == "MCV"
    assert labs.extract(row("MCV", "79")) == []


@pytest.mark.parametrize(
    "text",
    [
        "Test Result Unit Reference",
        "Date:12/08/2026",
        "Age/Sex: 62 / F",
        "Sample ID: SMP-0000",
        "12 Example Road, Demo Nagar · Tel 00000 00000",
        "Tab Metformin 500 mg BD x 30 days",
        "Admitted with fever and cough for 5 days. Treated with IV",
        "Sample: venous blood, fasting 10 hours.",
        "Review after 1 month with FBS report.",
    ],
)
def test_non_lab_lines_ignored(text: str) -> None:
    assert labs.extract(row(text)) == []


def test_single_ocr_line_row_and_glued_unit() -> None:
    e = one(row("Haemoglobin: 10.2g/dL (12.0 - 15.0)"))
    assert e["value"]["value"] == 10.2 and e["value"]["unit"] == "g/dL" and e["value"]["flag"] == "low"


def test_indian_thousands_separator() -> None:
    e = one(row("Platelet count", "1,50,000", "/cumm", "1,50,000-4,10,000"))
    assert e["value"]["value"] == 150000 and e["value"]["ref_high"] == 410000 and e["value"]["flag"] == "normal"


# ------------------------------------------------------------------ confidence and unreadable


def test_conf_is_row_min_and_bbox_is_union() -> None:
    cells = row("Haemoglobin", "10.2", "g/dL", "12.0-15.0")
    cells[1]["conf"] = 0.8
    e = one(cells)
    assert e["conf"] == 0.8 and e["readable"] is True
    assert e["bbox"] == document.union_bbox([c["bbox"] for c in cells])


def test_low_conf_row_unreadable() -> None:
    e = one(row("Haemoglobin", "10.2", "g/dL", "12.0-15.0", conf=0.55))
    assert e["readable"] is False and e["conf"] == 0.55
    assert e["value"]["value"] is None and e["value"]["flag"] == "unknown" and e["value"]["readable"] is False
    assert "unreadable" in e["text_en"] and "10.2" not in e["text_en"]


def test_garbled_digits_never_guessed() -> None:
    e = one(row("Haemoglobin", "1O.2", "g/dL", "12.0-15.0"))
    assert e["readable"] is False and e["value"]["value"] is None and e["value"]["test"] == "Haemoglobin"


def test_rows_grouped_from_cells() -> None:
    lines = row("Haemoglobin", "10.2", "g/dL", "12.0-15.0", y=100) + row("TLC", "7.8", "x10^3/uL", "4.0-11.0", y=150)
    ents = labs.extract(lines)
    assert [e["value"]["test"] for e in ents] == ["Haemoglobin", "WBC count"]


# ------------------------------------------------------------------ real samples

real_engine = test_document.real_engine  # one shared RapidOCR instance per test session


def _labs_of(name: str, ocr: document.OcrEngine) -> dict[str, dict]:
    path = settings.content_dir / "samples" / name
    if not path.exists():
        pytest.skip(f"sample {path} missing")
    out = document.process(path.read_bytes(), ocr)
    return {e.value["test"]: e.model_dump() for e in out.entities if e.kind == "lab"}


@pytest.mark.parametrize("name", ["lab_report_cbc.png", "lab_report_cbc_photo.png"])
def test_cbc_sample_haemoglobin_low(real_engine: document.OcrEngine, name: str) -> None:
    found = _labs_of(name, real_engine)
    hb = found["Haemoglobin"]
    assert hb["readable"] is True and hb["text_en"] == "Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW"
    assert hb["value"] == {"test": "Haemoglobin", "value": 10.2, "unit": "g/dL", "ref_low": 12.0, "ref_high": 15.0,
                           "flag": "low", "date": "2026-08-12"}  # fmt: skip
    assert found["Platelet count"]["value"]["flag"] == "normal"
    assert found["WBC count"]["value"]["value"] == 7.8
    assert len(found) == 6


def test_diabetes_sample(real_engine: document.OcrEngine) -> None:
    found = _labs_of("lab_report_diabetes.png", real_engine)
    assert {k: (v["value"]["value"], v["value"]["flag"]) for k, v in found.items()} == {
        "Fasting glucose": (142, "high"),
        "Post-prandial glucose": (198, "high"),
        "HbA1c": (7.4, "high"),
    }


@pytest.mark.parametrize("name", ["rx_allopathic.png", "discharge_summary.png", "handwritten_style.png"])
def test_no_labs_in_non_lab_documents(real_engine: document.OcrEngine, name: str) -> None:
    assert _labs_of(name, real_engine) == {}
