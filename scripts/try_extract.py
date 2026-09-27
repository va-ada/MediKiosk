"""Manual check of `/extract` logic against the REAL Ollama model (not used by tests).

    python3 scripts/try_extract.py "teen mahine se ghutne mein dard hai, bukhar nahi hai"
    python3 scripts/try_extract.py --question jp_fever "nahi, bukhar nahi hai"

If the NLP dependencies are not importable (e.g. system python3), the script re-runs itself with
`uv run --project nlp python scripts/try_extract.py ...` — you can also call that directly.
Default slots: site, duration_days, swelling, fever, injury, severity (from content/questions/joint_pain.yaml).
`--question <id>` uses only that question's slot, like the server does.
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NLP_DIR = REPO / "nlp"

try:
    import httpx  # noqa: F401
    import pydantic_settings  # noqa: F401
    import yaml
except ImportError:
    if os.environ.get("TRY_EXTRACT_REEXEC"):
        raise
    os.environ["TRY_EXTRACT_REEXEC"] = "1"
    os.execvp("uv", ["uv", "run", "--quiet", "--project", str(NLP_DIR), "python", __file__, *sys.argv[1:]])

import argparse
import asyncio
import json
import time

sys.path.insert(0, str(NLP_DIR))
from app.config import settings
from app.extract import ExtractIn, SlotSpec, extract

DEFAULT_SLOTS = ["site", "duration_days", "swelling", "fever", "injury", "severity"]


def slot_of(q: dict) -> SlotSpec:
    enum = [c["value"] for c in q.get("choices", [])] if q["slot"]["type"] in ("enum", "list_enum") else None
    return SlotSpec(name=q["slot"]["name"], type=q["slot"]["type"], enum=enum)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("text")
    ap.add_argument("--question", help="question id from joint_pain.yaml (default: several joint-pain slots)")
    ap.add_argument("--language", default="hi", choices=["hi", "en"])
    args = ap.parse_args()

    graph = yaml.safe_load((settings.content_dir / "questions" / "joint_pain.yaml").read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in graph["questions"]}
    if args.question:
        q = by_id[args.question]
        req = ExtractIn(
            question_id=q["id"], language=args.language, text=args.text,
            question_text_en=q["text_en"], slots=[slot_of(q)],
        )  # fmt: skip
    else:
        by_slot = {q["slot"]["name"]: q for q in graph["questions"]}
        req = ExtractIn(
            question_id="try_extract", language=args.language, text=args.text,
            question_text_en="Tell us about your joint pain.",
            slots=[slot_of(by_slot[s]) for s in DEFAULT_SLOTS],
        )  # fmt: skip

    print(f"model: {settings.ollama_model} @ {settings.ollama_url}")
    t0 = time.perf_counter()
    out = asyncio.run(extract(req))
    print(json.dumps(out.model_dump(), ensure_ascii=False, indent=2))
    print(f"took {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
