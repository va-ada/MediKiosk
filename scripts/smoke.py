"""End-to-end smoke test against the LIVE services (D3). Prints PASS/FAIL + timing per step; exit 1 on failure.

Run (all services up: make db-up server nlp his; island mode off):
    cd server && uv run python ../scripts/smoke.py
Options: --server http://localhost:8000 --nlp http://localhost:8001 --his http://localhost:8002

Journey: health → register → session → consent → triage → answer every question by tap → upload the CBC
sample (skipped if NLP is down) → read-back "yes" → submit → doctor login → call + in → open and approve
every section → outcome out → outbox reaches `sent` (≤ 20 s) → mock HIS lists the bundle → audit chain valid.

Note: the doctor calls THIS patient's token directly instead of `POST /api/queue/next`, because after a
demo reset "next" correctly picks someone else (e.g. a reserved recheck) — the selector itself is covered
by server/tests/test_queue.py.
"""

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False,
            "fainted": False}


class Smoke:
    def __init__(self) -> None:
        self.failed = False
        self.ctx: dict[str, Any] = {}

    def step(self, name: str, fn: Callable[[], str | None]) -> None:
        if self.failed:
            print(f"  SKIP  {name}")
            return
        t = time.perf_counter()
        try:
            detail = fn() or ""
            print(f"  PASS  {name:<34} {1000 * (time.perf_counter() - t):7.0f} ms  {detail}")
        except Exception as exc:  # noqa: BLE001  report any failure as FAIL and stop
            self.failed = True
            print(f"  FAIL  {name:<34} {1000 * (time.perf_counter() - t):7.0f} ms  {type(exc).__name__}: {exc}")


def ok(res: httpx.Response) -> Any:
    if res.status_code >= 400:
        raise AssertionError(f"HTTP {res.status_code}: {res.text[:200]}")
    return res.json() if res.content else None


def tap_value(q: dict[str, Any]) -> Any:
    """A sensible tap for each question type (first choice / neutral defaults, no branches into extra detail)."""
    values = [c["value"] for c in q["choices"]]
    return {
        "choice": lambda: values[0],
        "multi": lambda: ["none"] if "none" in values else values[:1],
        "yesno": lambda: False,
        "number": lambda: 7,
        "duration": lambda: 30,
        "scale": lambda: 3,
        "free": lambda: "none" if "none" in values else "Paracetamol 650",
    }[q["type"]]()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://localhost:8000")
    ap.add_argument("--nlp", default="http://localhost:8001")
    ap.add_argument("--his", default="http://localhost:8002")
    a = ap.parse_args()
    c = httpx.Client(base_url=a.server, timeout=60)
    s = Smoke()
    x = s.ctx
    print(f"MediKiosk smoke test → {a.server}")

    def health() -> str:
        assert ok(c.get("/api/health"))["status"] == "ok"
        return "server ok"

    def register() -> str:
        p = ok(c.post("/api/patients/register", headers=K,
                      json={"name": "Smoke Test", "age": 55, "sex": "F", "language": "hi"}))
        x["pid"] = p["id"]
        return p["hospital_id"]

    def session() -> str:
        x["sid"] = ok(c.post("/api/sessions", headers=K, json={"patient_id": x["pid"], "informant": "self"}))["id"]
        return x["sid"][:8]

    def consent() -> str:
        ok(c.post(f"/api/sessions/{x['sid']}/consent", headers=K, json={"capture": True, "scan": True,
               "share_hospital": True, "link_abha": False, "check_passed": True}))
        return "consented"

    def triage() -> str:
        r = ok(c.post(f"/api/sessions/{x['sid']}/triage", headers=K,
                      json={"complaint_code": "joint_pain", "complaint_text": "ghutne mein dard", "redflags": NO_FLAGS}))
        x["token"] = r["token"]
        assert r["session"]["status"] == "triaged"
        return f"token {r['token']['display']} ({r['token']['department']})"

    def answer_all() -> str:
        r, n = ok(c.get(f"/api/sessions/{x['sid']}/next-question?language=hi", headers=K)), 0
        while not r["done"]:
            q = r["question"]
            r = ok(c.post(f"/api/sessions/{x['sid']}/answers", headers=K,
                          json={"question_id": q["id"], "source": "tap", "value": tap_value(q)}))["next"]
            n += 1
            assert n < 100, "question loop did not end"
        return f"{n} questions"

    def upload() -> str:
        try:
            nlp_up = httpx.get(f"{a.nlp}/health", timeout=3).status_code == 200
        except httpx.HTTPError:
            nlp_up = False
        if not nlp_up:
            return "SKIPPED (NLP down)"
        img = (ROOT / "content/samples/lab_report_cbc.png").read_bytes()
        d = ok(c.post(f"/api/sessions/{x['sid']}/documents", headers=K, data={"page_no": "1"},
                      files={"image": ("cbc.png", img, "image/png")}))
        deadline = time.time() + 60
        while d["status"] == "pending" and time.time() < deadline:
            time.sleep(0.5)
            d = ok(c.get(f"/api/documents/{d['id']}", headers=K))
        assert d["status"] == "processed", f"document {d['status']}"
        return f"{d['doc_type']} {d['doc_date']} pinned={d['pinned']}"

    def readback() -> str:
        items = ok(c.get(f"/api/sessions/{x['sid']}/readback?language=hi", headers=K))["items"]
        for it in items:
            ok(c.post(f"/api/sessions/{x['sid']}/readback", headers=K, json={"fact_id": it["fact_id"], "response": "yes"}))
        return f"{len(items)} items confirmed"

    def submit() -> str:
        r = ok(c.post(f"/api/sessions/{x['sid']}/submit", headers=K))
        return f"summary v{r['summary_version']}"

    def login() -> str:
        x["doc"] = {"Authorization": "Bearer " + ok(c.post("/api/staff/login",
                                                           json={"staff_id": "D1", "pin": "1111"}))["token"]}
        x["adm"] = {"Authorization": "Bearer " + ok(c.post("/api/staff/login",
                                                           json={"staff_id": "A1", "pin": "5555"}))["token"]}
        return "D1 + A1"

    def call_in() -> str:
        tid = x["token"]["id"]
        assert ok(c.post(f"/api/tokens/{tid}/call", headers=x["doc"]))["status"] == "called"
        assert ok(c.post(f"/api/tokens/{tid}/in", headers=x["doc"]))["status"] == "in"
        return x["token"]["display"]

    def review() -> str:
        summ = ok(c.get(f"/api/sessions/{x['sid']}/summary", headers=x["doc"]))
        keys = [sec["key"] for sec in summ["sections"]]
        for key in keys:
            ok(c.post(f"/api/sessions/{x['sid']}/sections/{key}/open", headers=x["doc"]))
            ok(c.post(f"/api/sessions/{x['sid']}/sections/{key}/approve", headers=x["doc"]))
        after = ok(c.get(f"/api/sessions/{x['sid']}/summary", headers=x["doc"]))
        assert all(sec["approved"] for sec in after["sections"]), "not every section approved"
        trusts = {i["trust"] for sec in after["sections"] for i in sec["items"]}
        assert trusts == {"doctor_verified"}, trusts
        return f"{len(keys)} sections approved (v{after['version']})"

    def outcome() -> str:
        assert ok(c.post(f"/api/tokens/{x['token']['id']}/outcome", headers=x["doc"],
                         json={"outcome": "out", "note": "smoke test"}))["status"] == "done"
        return "done"

    def outbox_sent() -> str:
        if ok(c.get("/api/admin/island", headers=x["adm"]))["enabled"]:
            raise AssertionError("island mode is ON — turn it off in /admin, then re-run")
        deadline, row = time.time() + 20, None
        while time.time() < deadline:
            row = next((o for o in ok(c.get("/api/admin/outbox", headers=x["adm"])) if o["session_id"] == x["sid"]), None)
            if row and row["status"] == "sent":
                x["key"] = row["idempotency_key"]
                return f"{row['idempotency_key'].split(':')[1]} · {row['resource_count']} resources · attempts {row['attempts']}"
            time.sleep(1)
        raise AssertionError(f"outbox not sent after 20 s: {row and (row['status'], row['last_error'])}")

    def his_has_it() -> str:
        bundles = ok(httpx.get(f"{a.his}/bundles", timeout=5))
        assert any(b.get("idempotency_key") == x["key"] for b in bundles), "bundle not found in mock HIS"
        return f"{len(bundles)} bundle(s) in HIS"

    def audit_valid() -> str:
        v = ok(c.get("/api/admin/audit/verify", headers=x["adm"]))
        assert v["valid"], f"chain broken at id {v['first_bad_id']}"
        return f"{v['checked']} entries"

    for name, fn in [("health", health), ("register patient", register), ("create session", session),
                     ("consent", consent), ("triage → token", triage), ("answer every question (tap)", answer_all),
                     ("upload CBC report", upload), ("read-back yes", readback), ("submit", submit),
                     ("staff login", login), ("call + in", call_in), ("open + approve all sections", review),
                     ("outcome out", outcome), ("outbox → sent (≤ 20 s)", outbox_sent),
                     ("mock HIS lists the bundle", his_has_it), ("audit chain valid", audit_valid)]:
        s.step(name, fn)
    print("RESULT:", "FAIL" if s.failed else "PASS")
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())
