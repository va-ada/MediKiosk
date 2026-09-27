"""Document reading (`POST /document`): RapidOCR lines, doc_type by keyword score, doc_date, then entities
from `labs.extract` / `rx.extract` when those modules exist.

Line dicts are `{text, bbox:[x,y,w,h], conf}` in ORIGINAL image pixels (after EXIF rotation, i.e. as a browser
shows the image). Internally a line also carries `quad` (the 4 OCR corner points) so extractors can undo page skew
in phone photos; the response model drops it.
"""

import importlib
import io
import logging
import re
import statistics
import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

log = logging.getLogger("nlp.document")

MAX_SIDE = 2400  # larger photos are downscaled for OCR (boxes are scaled back to original pixels)
DocType = Literal["lab_report", "prescription", "discharge_summary", "unknown"]


class ImageError(Exception):
    """The upload could not be decoded as an image."""


# --------------------------------------------------------------------------------------------------------------------
# Response models (CONTRACTS §6)
# --------------------------------------------------------------------------------------------------------------------


class LineOut(BaseModel):
    text: str
    bbox: list[int]
    conf: float


class EntityOut(BaseModel):
    kind: Literal["lab", "drug", "diagnosis"]
    value: dict[str, Any]
    text_en: str
    bbox: list[int] | None
    conf: float
    readable: bool


class DocumentOut(BaseModel):
    doc_type: DocType
    doc_date: str | None
    lines: list[LineOut]
    entities: list[EntityOut]


# --------------------------------------------------------------------------------------------------------------------
# Geometry helpers (shared by labs.py / rx.py)
# --------------------------------------------------------------------------------------------------------------------


def quad_to_bbox(quad: Any, scale: float = 1.0) -> list[int]:
    xs = [float(p[0]) * scale for p in quad]
    ys = [float(p[1]) * scale for p in quad]
    x, y = round(min(xs)), round(min(ys))
    return [x, y, round(max(xs)) - x, round(max(ys)) - y]


def union_bbox(boxes: list[list[int]]) -> list[int] | None:
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
    return [x0, y0, x1 - x0, y1 - y0]


def page_skew(lines: list[dict]) -> float:
    """Median baseline slope (dy/dx) of wide text lines; 0 when no line has a quad (e.g. synthetic fixtures)."""
    slopes = []
    for ln in lines:
        q = ln.get("quad")
        if not q:
            continue
        dx, dy = float(q[1][0]) - float(q[0][0]), float(q[1][1]) - float(q[0][1])
        w, h = ln["bbox"][2], ln["bbox"][3]
        if dx > 0 and w > 3 * h:  # wide lines give a stable angle
            slopes.append(dy / dx)
    return statistics.median(slopes) if slopes else 0.0


def group_rows(lines: list[dict]) -> list[list[dict]]:
    """Group OCR boxes into visual rows (table cells → one row), top to bottom, each row left to right.

    Page skew is undone first, so a tilted phone photo still groups a table row's cells together."""
    if not lines:
        return []
    skew = page_skew(lines)

    def key(ln: dict) -> float:
        x, y, w, h = ln["bbox"]
        return (y + h / 2) - skew * (x + w / 2)

    heights = sorted(ln["bbox"][3] for ln in lines)
    tol = max(heights[len(heights) // 2] * 0.5, 4)
    rows: list[list[dict]] = []
    centres: list[float] = []
    for ln in sorted(lines, key=key):
        k = key(ln)
        if rows and abs(k - centres[-1]) <= tol:
            rows[-1].append(ln)
            centres[-1] = sum(key(r) for r in rows[-1]) / len(rows[-1])
        else:
            rows.append([ln])
            centres.append(k)
    return [sorted(r, key=lambda ln: ln["bbox"][0]) for r in rows]


# --------------------------------------------------------------------------------------------------------------------
# Classification and date
# --------------------------------------------------------------------------------------------------------------------

# Keyword → weight. Distinct keywords count once each, so a list of five "Tab" lines doesn't outweigh a title.
KEYWORDS: dict[str, dict[str, int]] = {
    "lab_report": {
        "hb": 1, "haemoglobin": 1, "hemoglobin": 1, "mg/dl": 1, "g/dl": 1, "reference": 1, "range": 1, "test": 1,
    },
    "prescription": {"rx": 1, "tab": 1, "cap": 1, "syp": 1, "od": 1, "bd": 1, "tds": 1, "sos": 1},
    "discharge_summary": {"discharge": 1, "admitted": 1, "diagnosis": 1, "summary": 1, "discharge summary": 3},
}  # fmt: skip
_TIE_ORDER = ["discharge_summary", "lab_report", "prescription"]  # a discharge summary also lists medicines/labs
MIN_SCORE = 2


def _kw_pattern(kw: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])")


_KW_RE = {t: {kw: _kw_pattern(kw) for kw in kws} for t, kws in KEYWORDS.items()}


def classify(lines: list[dict]) -> DocType:
    text = "\n".join(ln["text"] for ln in lines).lower()
    text = re.sub(r"(?<=[a-z])\.(?=\s|$)", "", text)  # "Tab." → "tab"
    scores = {t: sum(w for kw, w in KEYWORDS[t].items() if _KW_RE[t][kw].search(text)) for t in KEYWORDS}
    best = max(_TIE_ORDER, key=lambda t: scores[t])  # max() keeps the first of equal scores → tie order
    return best if scores[best] >= MIN_SCORE else "unknown"  # type: ignore[return-value]


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}  # fmt: skip
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})(?!\d)")
_TEXT_DATE = re.compile(r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?[\s\-]*([A-Za-z]{3,9})\.?[\s\-,]*(\d{4})(?!\d)")


def _mk_date(d: int, m: int, y: int) -> date | None:
    if y < 100:
        y += 2000
    try:
        return date(y, m, d)
    except ValueError:
        return None


def parse_date(text: str) -> date | None:
    """First date in `text`: dd/mm/yyyy, dd-mm-yy, dd.mm.yyyy (Indian day-first) or "12 Aug 2026"."""
    found: list[tuple[int, date]] = []
    for m in _NUMERIC_DATE.finditer(text):
        if dt := _mk_date(int(m.group(1)), int(m.group(2)), int(m.group(3))):
            found.append((m.start(), dt))
    for m in _TEXT_DATE.finditer(text):
        month = _MONTHS.get(m.group(2)[:3].lower())
        if month and (dt := _mk_date(int(m.group(1)), month, int(m.group(3)))):
            found.append((m.start(), dt))
    return min(found)[1] if found else None


def find_date(lines: list[dict]) -> str | None:
    """doc_date: the first date in reading order, preferring a line labelled "Date" (not "Date of birth")."""
    ordered = [
        ln for row in group_rows(lines) for ln in row if not re.search(r"birth|\bdob\b", ln["text"], re.IGNORECASE)
    ]
    labelled = [ln for ln in ordered if re.search(r"\bdate\b", ln["text"], re.IGNORECASE)]
    for pool in (labelled, ordered):
        for ln in pool:
            if dt := parse_date(ln["text"]):
                return dt.isoformat()
    return None


# --------------------------------------------------------------------------------------------------------------------
# OCR engine
# --------------------------------------------------------------------------------------------------------------------


def _load_rapidocr() -> Any:
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


class OcrEngine:
    """RapidOCR, loaded once (lazily on first use, or via `start_loading()` in a background thread)."""

    def __init__(self, loader: Callable[[], Any] = _load_rapidocr) -> None:
        self._loader = loader
        self.model: Any = None
        self.error: str | None = None
        self._load_lock = threading.Lock()
        self._infer_lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self.model is not None

    def start_loading(self) -> None:
        threading.Thread(target=self.ensure_loaded, name="ocr-loader", daemon=True).start()

    def ensure_loaded(self) -> bool:
        with self._load_lock:
            if self.model is None:
                t0 = time.monotonic()
                try:
                    self.model = self._loader()
                    self.error = None
                    log.info("OCR engine loaded in %.1f s", time.monotonic() - t0)
                except Exception as exc:  # noqa: BLE001 — report as 503, never crash the service
                    self.error = f"{type(exc).__name__}: {exc}"
                    log.error("OCR engine failed to load: %s", self.error)
        return self.model is not None

    def read(self, img: Any) -> list[tuple[Any, str, float]]:
        """Run OCR on an RGB numpy array → [(quad, text, conf)]."""
        with self._infer_lock:
            result, _ = self.model(img)
        return [(q, str(t), float(c)) for q, t, c in (result or [])]


engine = OcrEngine()


def load_image(data: bytes) -> Any:
    """Decode upload bytes → (PIL RGB image with EXIF orientation applied)."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    if not data:
        raise ImageError("Empty image upload")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageError("Could not decode image (expected JPEG/PNG/WebP)") from exc
    return ImageOps.exif_transpose(img).convert("RGB")


def ocr_lines(img: Any, ocr: OcrEngine | None = None) -> list[dict]:
    """OCR a PIL image → line dicts (bbox in the image's own pixels)."""
    import numpy as np

    ocr = ocr or engine
    scale = 1.0
    work = img
    if max(img.size) > MAX_SIDE:
        scale = max(img.size) / MAX_SIDE
        work = img.resize((round(img.width / scale), round(img.height / scale)))
    lines = []
    for quad, text, conf in ocr.read(np.asarray(work)):
        text = text.strip()
        if not text:
            continue
        orig_quad = [[float(p[0]) * scale, float(p[1]) * scale] for p in quad]
        lines.append({"text": text, "bbox": quad_to_bbox(orig_quad), "conf": round(conf, 3), "quad": orig_quad})
    return lines


def extract_entities(lines: list[dict], doc_date: str | None) -> list[dict]:
    """`labs.extract(lines)` + `rx.extract(lines)` for whichever of those modules exists."""
    entities: list[dict] = []
    for name in ("labs", "rx"):
        try:
            mod = importlib.import_module(f"app.{name}")
        except ModuleNotFoundError as exc:
            if exc.name != f"app.{name}":
                raise
            continue
        entities.extend(mod.extract(lines, doc_date=doc_date))
    return entities


def process(data: bytes, ocr: OcrEngine | None = None) -> DocumentOut:
    lines = ocr_lines(load_image(data), ocr)
    doc_date = find_date(lines)
    return DocumentOut(
        doc_type=classify(lines),
        doc_date=doc_date,
        lines=[LineOut(text=ln["text"], bbox=ln["bbox"], conf=ln["conf"]) for ln in lines],
        entities=[EntityOut(**e) for e in extract_entities(lines, doc_date)],
    )
