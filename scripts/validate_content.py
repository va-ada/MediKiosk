"""Validate everything under content/ against CONTRACTS.md §2 and §9.

Usage:  python3 scripts/validate_content.py        → prints OK, or every error and exits 1.
"""

import sys
from pathlib import Path
from typing import Any

import yaml

CONTENT = Path(__file__).resolve().parents[1] / "content"

QUESTION_TYPES = {"choice", "multi", "yesno", "number", "duration", "scale", "free"}
SLOT_TYPES = {"string", "enum", "bool", "number", "duration_days", "scale_0_10", "list_enum", "list_string"}
SECTIONS = {"complaint", "hpi", "pmh", "drugs", "allergies", "family", "personal", "ros", "labs", "ayush"}
DEPARTMENTS = {"general", "ayurveda"}
COMPLAINT_CODES = {"joint_pain", "fever", "cough", "stomach", "headache", "chest_pain", "breathing", "skin", "other"}
REDFLAG_SLOTS = ["chest_pain", "breathless", "stroke_signs", "heavy_bleeding", "fainted"]
CONDITION_OPS = {"is", "in", "gte", "lte"}
# question type → slot types that make sense for it
TYPE_SLOTS = {
    "choice": {"enum", "string"},
    "multi": {"list_enum"},
    "yesno": {"bool"},
    "number": {"number"},
    "duration": {"duration_days"},
    "scale": {"scale_0_10"},
    "free": {"string", "list_string"},
}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")


def load_yaml(path: Path, rep: Report) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        rep.err(path.name, f"cannot load: {exc}")
        return None


def check_condition(where: str, cond: Any, rep: Report) -> None:
    if not isinstance(cond, dict) or "slot" not in cond:
        rep.err(where, f"condition needs a slot: {cond!r}")
        return
    ops = set(cond) - {"slot"}
    if len(ops) != 1 or not ops <= CONDITION_OPS:
        rep.err(where, f"condition needs exactly one of {sorted(CONDITION_OPS)}: {cond!r}")


def check_questions(rep: Report) -> dict[str, dict]:
    """Returns {pathway_id: {"slots": set, "questions": {...}}}."""
    pathways: dict[str, dict] = {}
    seen_ids: dict[str, str] = {}
    for path in sorted((CONTENT / "questions").glob("*.yaml")):
        where = f"questions/{path.name}"
        doc = load_yaml(path, rep)
        if not isinstance(doc, dict):
            rep.err(where, "top level must be a mapping")
            continue
        if doc.get("id") != path.stem:
            rep.err(where, f"id {doc.get('id')!r} must equal the file name {path.stem!r}")
        questions = doc.get("questions") or []
        if not isinstance(questions, list) or not questions:
            rep.err(where, "needs a non-empty questions list")
            continue
        ids = {q.get("id") for q in questions if isinstance(q, dict)}
        if doc.get("start") not in ids:
            rep.err(where, f"start {doc.get('start')!r} is not a question id")
        slots: set[str] = set()
        for q in questions:
            qid = q.get("id") if isinstance(q, dict) else None
            qw = f"{where}#{qid}"
            if not qid:
                rep.err(where, f"question without id: {q!r}")
                continue
            if qid in seen_ids:
                rep.err(qw, f"duplicate id (also in {seen_ids[qid]})")
            seen_ids[qid] = where
            for field in ("text_en", "text_hi"):
                if not str(q.get(field) or "").strip():
                    rep.err(qw, f"missing {field}")
            qtype = q.get("type")
            if qtype not in QUESTION_TYPES:
                rep.err(qw, f"bad type {qtype!r}")
            if q.get("section") not in SECTIONS:
                rep.err(qw, f"bad section {q.get('section')!r}")
            if doc.get("id") == "ayush" and q.get("section") != "ayush":
                rep.err(qw, "every ayush question must have section: ayush")
            slot = q.get("slot") or {}
            if not slot.get("name"):
                rep.err(qw, "slot.name missing")
            else:
                slots.add(slot["name"])
            if slot.get("type") not in SLOT_TYPES:
                rep.err(qw, f"bad slot type {slot.get('type')!r}")
            elif qtype in TYPE_SLOTS and slot["type"] not in TYPE_SLOTS[qtype]:
                rep.err(qw, f"slot type {slot['type']!r} does not fit question type {qtype!r}")
            choices = q.get("choices")
            if qtype in {"choice", "multi"} and not choices:
                rep.err(qw, f"{qtype} question needs choices")
            if choices is not None:
                if not isinstance(choices, list):
                    rep.err(qw, "choices must be a list")
                else:
                    values = []
                    for c in choices:
                        if not isinstance(c, dict) or "value" not in c or not c.get("en") or not c.get("hi"):
                            rep.err(qw, f"choice needs value, en and hi: {c!r}")
                        else:
                            values.append(c["value"])
                    if len(values) != len(set(map(str, values))):
                        rep.err(qw, "duplicate choice values")
            nxt = q.get("next")
            targets: list[str] = []
            if isinstance(nxt, str):
                targets = [nxt]
            elif isinstance(nxt, list) and nxt:
                for i, rule in enumerate(nxt):
                    if not isinstance(rule, dict) or "goto" not in rule:
                        rep.err(qw, f"next rule {i} needs goto")
                        continue
                    targets.append(rule["goto"])
                    if "if" in rule:
                        check_condition(f"{qw} next[{i}]", rule["if"], rep)
                    elif i != len(nxt) - 1:
                        rep.err(qw, f"next rule {i} has no 'if' but is not the last (default) rule")
                if "if" in nxt[-1]:
                    rep.err(qw, "last next rule must be a default (no 'if')")
            else:
                rep.err(qw, "next must be a question id, 'end', or a rule list")
            for t in targets:
                if t != "end" and t not in ids:
                    rep.err(qw, f"next target {t!r} does not exist in this file")
        pathways[doc.get("id") or path.stem] = {"slots": slots, "questions": questions}
    return pathways


def check_triage(rep: Report, pathways: dict[str, dict]) -> None:
    doc = load_yaml(CONTENT / "triage.yaml", rep)
    if not isinstance(doc, dict):
        rep.err("triage.yaml", "missing or not a mapping")
        return
    codes = []
    for c in doc.get("complaints") or []:
        w = f"triage.yaml#{c.get('code')}"
        codes.append(c.get("code"))
        if c.get("code") not in COMPLAINT_CODES:
            rep.err(w, "unknown complaint code")
        if c.get("department") not in DEPARTMENTS:
            rep.err(w, f"bad department {c.get('department')!r}")
        for f in ("icon", "en", "hi"):
            if not c.get(f):
                rep.err(w, f"missing {f}")
        if c.get("pathway") is not None and c["pathway"] not in pathways:
            rep.err(w, f"pathway {c['pathway']!r} has no questions/{c['pathway']}.yaml")
    missing = COMPLAINT_CODES - set(codes)
    if missing:
        rep.err("triage.yaml", f"complaint codes missing: {sorted(missing)}")
    if len(codes) != len(set(codes)):
        rep.err("triage.yaml", "duplicate complaint codes")
    slots = [q.get("slot") for q in doc.get("redflag_questions") or []]
    if slots != REDFLAG_SLOTS:
        rep.err("triage.yaml", f"redflag_questions must be exactly {REDFLAG_SLOTS} in order, got {slots}")
    for q in doc.get("redflag_questions") or []:
        if not q.get("en") or not q.get("hi"):
            rep.err(f"triage.yaml#{q.get('slot')}", "red-flag question needs en and hi")


def main() -> int:
    rep = Report()
    pathways = check_questions(rep)
    check_triage(rep, pathways)
    if rep.errors:
        print(f"{len(rep.errors)} error(s):")
        for e in rep.errors:
            print(f"  - {e}")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
