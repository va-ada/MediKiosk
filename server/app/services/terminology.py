"""Diagnosis-code search over content/terminology.csv (placeholder SAMPLE-* codes in the MVP)."""

import csv
from functools import lru_cache
from typing import Any

from rapidfuzz import fuzz, process, utils

from app.config import settings

MIN_SCORE = 60
MAX_RESULTS = 10


@lru_cache
def rows() -> list[dict[str, Any]]:
    with (settings.content_dir / "terminology.csv").open(encoding="utf-8", newline="") as f:
        return [
            {
                "system": r["system"],
                "code": r["code"],
                "display": r["display"],
                "sample": str(r.get("sample", "")).strip().lower() == "true",
            }
            for r in csv.DictReader(f)
        ]


def search(q: str, system: str | None = None, data: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """rapidfuzz WRatio over "display code"; top 10 with score ≥ 60, best first."""
    q = q.strip()
    if not q:
        return []
    pool = [r for r in (data if data is not None else rows()) if not system or r["system"] == system]
    choices = [f"{r['display']} {r['code']}" for r in pool]
    hits = process.extract(
        q, choices, scorer=fuzz.WRatio, processor=utils.default_process, limit=None, score_cutoff=MIN_SCORE
    )
    needle = utils.default_process(q)

    def rank(hit: tuple[str, float, int]) -> tuple[int, float]:
        # Doctors type the start of a term ("sandhi"): word-prefix and substring hits outrank fuzzy ones.
        text = utils.default_process(hit[0])
        prefix = any(w.startswith(needle) for w in text.split())
        return (2 if prefix else 1 if needle in text else 0, hit[1])

    return [pool[i] for _, _, i in sorted(hits, key=rank, reverse=True)[:MAX_RESULTS]]
