import io
from pathlib import Path

import pytest

from app import document
from app.config import settings

SAMPLES = settings.content_dir / "samples"


def sample(name: str) -> Path:
    p = SAMPLES / name
    if not p.exists():
        pytest.skip(f"sample {p} missing (run scripts/make_samples.py)")
    return p


def L(text: str, y: int = 0, x: int = 0, conf: float = 0.99) -> dict:
    return {"text": text, "bbox": [x, y, 20 * len(text), 30], "conf": conf}


@pytest.fixture(scope="session")
def real_engine() -> document.OcrEngine:
    eng = document.OcrEngine()
    if not eng.ensure_loaded():
        pytest.skip(f"RapidOCR unavailable: {eng.error}")
    return eng


@pytest.fixture
def ocr_client(client, monkeypatch: pytest.MonkeyPatch, real_engine):
    monkeypatch.setattr(document, "engine", real_engine)
    return client


# ------------------------------------------------------------------ classification


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Test Result Unit Reference", "Haemoglobin 10.2 g/dL 12.0-15.0"], "lab_report"),
        (["Rx", "Tab Metformin 500 mg BD x 30 days", "Tab Amlodipine 5 mg OD"], "prescription"),
        (["DISCHARGE SUMMARY", "Final diagnosis: pneumonia", "Tab Amoxicillin 500 mg TDS", "Tab. Paracetamol SOS"],
         "discharge_summary"),
        (["Hello world", "Nothing medical here"], "unknown"),
        (["Diagnosis: Type 2 diabetes", "Rx", "Tab Metformin 500 mg BD"], "prescription"),
    ],
)  # fmt: skip
def test_classify(texts: list[str], expected: str) -> None:
    assert document.classify([L(t, y=40 * i) for i, t in enumerate(texts)]) == expected


def test_keywords_match_whole_words_only() -> None:
    # "food", "tablet-free", "testing" must not count as od / tab / test
    assert document.classify([L("good food"), L("testing tablets carefully")]) == "unknown"


# ------------------------------------------------------------------ dates


@pytest.mark.parametrize(
    ("text", "iso"),
    [
        ("Date:12/08/2026", "2026-08-12"),  # Indian day-first
        ("Date: 05-07-26", "2026-07-05"),
        ("on 3.3.2026", "2026-03-03"),
        ("Report date 12 Aug 2026", "2026-08-12"),
        ("12-August-2026", "2026-08-12"),
        ("1st Sep, 2026", "2026-09-01"),
        ("31/02/2026 is not a date", None),
        ("Tel 00000 00000", None),
    ],
)
def test_parse_date(text: str, iso: str | None) -> None:
    got = document.parse_date(text)
    assert (got.isoformat() if got else None) == iso


def test_find_date_prefers_labelled_line() -> None:
    lines = [L("Admitted 28/02/2026", y=0), L("Date: 03/03/2026", y=100), L("x 01/01/2020", y=200)]
    assert document.find_date(lines) == "2026-03-03"
    assert document.find_date([L("no dates"), L("ref 28/02/2026", y=50)]) == "2026-02-28"
    assert document.find_date([L("Date of birth: 01/01/1960"), L("Visit 02/02/2026", y=50)]) == "2026-02-02"


# ------------------------------------------------------------------ geometry


def test_group_rows_undoes_skew() -> None:
    # a table row tilted upwards to the right (slope -0.06), rows 40 px apart
    def cell(text: str, x: int, row: int) -> dict:
        y = 600 + 40 * row - 0.06 * x
        quad = [[x, y], [x + 150, y - 9], [x + 150, y + 21], [x, y + 30]]
        return {"text": text, "bbox": document.quad_to_bbox(quad), "conf": 1.0, "quad": quad}

    lines = [cell(t, x, r) for r, (a, b, c) in enumerate([("Haemoglobin", "10.2", "12.0-15.0"),
                                                          ("Total WBC count", "7.8", "4.0-11.0")])
             for t, x in ((a, 160), (b, 490), (c, 790))]  # fmt: skip
    rows = document.group_rows(lines)
    assert [[c["text"] for c in r] for r in rows] == [["Haemoglobin", "10.2", "12.0-15.0"],
                                                      ["Total WBC count", "7.8", "4.0-11.0"]]  # fmt: skip


def test_quad_to_bbox() -> None:
    assert document.quad_to_bbox([[10, 20], [110, 18], [111, 50], [11, 52]]) == [10, 18, 101, 34]


# ------------------------------------------------------------------ images and route


def test_load_image_rejects_garbage() -> None:
    with pytest.raises(document.ImageError):
        document.load_image(b"not an image")
    with pytest.raises(document.ImageError):
        document.load_image(b"")


def test_route_invalid_image(ocr_client) -> None:
    r = ocr_client.post("/document", files={"image": ("x.png", b"garbage", "image/png")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_image"


def test_route_503_when_ocr_cannot_load(client, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken() -> None:
        raise RuntimeError("onnx missing")

    monkeypatch.setattr(document, "engine", document.OcrEngine(loader=broken))
    r = client.post("/document", files={"image": ("x.png", b"x", "image/png")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_loading"
    assert client.get("/health").json()["ocr_loaded"] is False


def test_large_photo_boxes_in_original_pixels(real_engine) -> None:
    from PIL import Image

    img = Image.open(sample("lab_report_cbc.png")).convert("RGB")
    big = img.resize((img.width * 3, img.height * 3))  # 3720 px tall → downscaled for OCR, boxes scaled back
    lines = {ln["text"]: ln for ln in document.ocr_lines(big, real_engine)}
    x, y, w, _ = lines["Haemoglobin"]["bbox"]
    assert 200 < x < 260 and 1830 < y < 1900 and w > 250


def test_cbc_sample(ocr_client) -> None:
    with sample("lab_report_cbc.png").open("rb") as f:
        r = ocr_client.post("/document", files={"image": ("cbc.png", f, "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["doc_type"] == "lab_report" and body["doc_date"] == "2026-08-12"
    assert set(body) == {"doc_type", "doc_date", "lines", "entities"}
    texts = [ln["text"] for ln in body["lines"]]
    assert "Haemoglobin" in texts
    for ln in body["lines"]:
        assert (
            set(ln) == {"text", "bbox", "conf"} and len(ln["bbox"]) == 4 and all(isinstance(v, int) for v in ln["bbox"])
        )
        assert 0 <= ln["conf"] <= 1
    assert ocr_client.get("/health").json()["ocr_loaded"] is True


@pytest.mark.parametrize(
    ("name", "doc_type", "doc_date"),
    [
        ("lab_report_cbc_photo.png", "lab_report", "2026-08-12"),
        ("lab_report_diabetes.png", "lab_report", "2026-07-05"),
        ("rx_allopathic.png", "prescription", "2026-08-12"),
        ("rx_allopathic_photo.png", "prescription", "2026-08-12"),
        ("rx_ayurveda.png", "prescription", "2026-06-20"),
        ("discharge_summary.png", "discharge_summary", "2026-03-03"),
    ],
)
def test_samples_classified_and_dated(real_engine, name: str, doc_type: str, doc_date: str) -> None:
    out = document.process(sample(name).read_bytes(), real_engine)
    assert (out.doc_type, out.doc_date) == (doc_type, doc_date)
    assert out.lines


def test_png_roundtrip_bytes() -> None:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(buf, format="PNG")
    assert document.load_image(buf.getvalue()).size == (40, 20)
