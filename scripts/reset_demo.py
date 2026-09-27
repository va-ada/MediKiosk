"""Reset the database to the demo starting state (D2).

DESTRUCTIVE: drops every table. Asks you to type RESET unless --yes; refuses non-local databases.
Run:  make demo-reset        (or: cd server && uv run python ../scripts/reset_demo.py --yes)

Creates, through the real API routes (same validation + audit as a kiosk):
  - Kamla Devi (ABHA) — ayurveda, joint pain, complete history + AYUSH answers, read-back done, CBC report
    (sample image stored encrypted; lab facts inserted directly as from_report), submitted.
  - Rahul Verma (ABHA) — general, fever, triaged only.
  - Sita Sharma — ayurveda, seen by Dr. Mehta and sent for a recheck (priority, reserved for Dr. Mehta).
Also: island mode off, empty outbox, mock HIS inbox and old patient files cleared.
"""

import argparse
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app import db  # noqa: E402
from app.config import settings  # noqa: E402

K = {"X-Kiosk-Id": "KIOSK-01"}
NO_FLAGS = {"chest_pain": False, "breathless": False, "stroke_signs": False, "heavy_bleeding": False,
            "fainted": False}
CONSENT = {"capture": True, "scan": True, "share_hospital": True, "link_abha": True, "check_passed": True}
KAMLA_ANSWERS = [
    ("jp_site", "knee"), ("jp_side", "both"), ("jp_duration", 90), ("jp_onset", "gradual"),
    ("jp_character", "aching"), ("jp_swelling", True), ("jp_swelling_where", ["knee"]),
    ("jp_stiffness", "under_30"), ("jp_worse", ["stairs", "cold"]), ("jp_better", ["heat", "rest"]),
    ("jp_severity", 6), ("jp_fever", False), ("jp_injury", False), ("jp_other_joints", ["none"]),
    ("jp_medicines", "Paracetamol 650"), ("jp_allergy", True), ("jp_allergy_detail", "Penicillin — rash"),
    ("ay_appetite", "low"), ("ay_quantity", "less"), ("ay_exercise", "10_30"), ("ay_suits", ["warm_food"]),
    ("ay_upsets", ["cold_weather", "curd"]), ("ay_digestion", ["gas"]), ("ay_bowel_freq", "alternate_days"),
    ("ay_bowel_type", "hard"), ("ay_meal_times", False), ("ay_diet", "veg"), ("ay_spicy", "weekly"),
    ("ay_sleep_hours", 6), ("ay_day_sleep", True), ("ay_triggers", ["cold_weather", "long_sitting"]),
    ("pk_frame", "thin"), ("pk_skin", "dry"), ("pk_appetite", "irregular"), ("pk_sleep", "light"),
    ("pk_temperament", "changeable"), ("pk_weather", "cold"),
]
CBC_LABS = [  # from content/samples/lab_report_cbc.png (fictional sample data)
    ("Haemoglobin", 10.2, "g/dL", 12.0, 15.0, "low"), ("WBC count", 7.8, "x10^3/uL", 4.0, 11.0, "normal"),
    ("Platelet count", 210, "x10^3/uL", 150, 410, "normal"), ("PCV (Haematocrit)", 32.5, "%", 36.0, 46.0, "low"),
    ("MCV", 79, "fL", 83, 101, "low"),
]


def ok(res, what: str) -> dict:
    if res.status_code >= 400:
        sys.exit(f"FAILED {what}: {res.status_code} {res.text[:300]}")
    return res.json() if res.content else {}


def confirm(args: argparse.Namespace) -> None:
    host = urlparse(settings.database_url.replace("+psycopg", "")).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        sys.exit(f"Refusing to reset a non-local database ({host}).")
    if not args.yes:
        print(f"This DELETES every table in {settings.database_url.rsplit('@', 1)[-1]} and all patient files.")
        if input("Type RESET to continue: ").strip() != "RESET":
            sys.exit("Aborted.")


def wipe_files() -> None:
    for sub in ("patients", "his"):
        target = settings.data_dir / sub
        if target.exists():
            shutil.rmtree(target)


def new_visit(c: TestClient, patient_id: str, complaint: str, text: str | None = None) -> tuple[str, dict]:
    sid = ok(c.post("/api/sessions", json={"patient_id": patient_id, "informant": "self"}, headers=K), "session")["id"]
    ok(c.post(f"/api/sessions/{sid}/consent", json=CONSENT, headers=K), "consent")
    tri = ok(c.post(f"/api/sessions/{sid}/triage", headers=K,
                    json={"complaint_code": complaint, "complaint_text": text, "redflags": NO_FLAGS}), "triage")
    return sid, tri["token"]


def add_cbc(session_id: str, patient_id: str) -> None:
    from app.models import Document, Fact
    from app.services.files import store_file

    with Session(db.engine) as s:
        doc = Document(session_id=session_id, patient_id=patient_id, file_path="", page_no=1,
                       doc_type="lab_report", status="processed", pinned=True)
        doc.file_path = store_file(patient_id, f"docs/{doc.id}.bin",
                                   (ROOT / "content/samples/lab_report_cbc.png").read_bytes())
        from datetime import date

        doc.doc_date = date(2026, 8, 12)
        s.add(doc)
        s.flush()
        for test, value, unit, lo, hi, flag in CBC_LABS:
            text = f"{test} {value:g} {unit} (ref {lo:g}–{hi:g})" + (f" {flag.upper()}" if flag != "normal" else "")
            s.add(Fact(session_id=session_id, patient_id=patient_id, section="labs", key=test, trust="from_report",
                       source_type="document", source_id=doc.id, text_en=text,
                       value={"test": test, "value": value, "unit": unit, "ref_low": lo, "ref_high": hi,
                              "flag": flag, "date": "2026-08-12"}))
        from app import audit

        audit.record(s, "system", "demo.cbc_inserted", "document", doc.id, {"labs": len(CBC_LABS)})
        s.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args()
    confirm(args)
    settings.run_workers = False

    from app import models  # noqa: F401
    from app.main import app

    sys.path.insert(0, str(ROOT / "scripts"))
    from seed import seed

    print("Dropping and recreating tables…")
    SQLModel.metadata.drop_all(db.engine)
    SQLModel.metadata.create_all(db.engine)
    wipe_files()
    with Session(db.engine) as s:
        seed(s)

    c = TestClient(app)
    login = lambda sid, pin: {"Authorization": "Bearer " + ok(  # noqa: E731
        c.post("/api/staff/login", json={"staff_id": sid, "pin": pin}), f"login {sid}")["token"]}
    mehta = login("D1", "1111")

    # 1. Kamla Devi — full history, read-back, CBC, submitted
    kamla = ok(c.post("/api/patients/abha/verify", json={"abha_number": "12345678901234", "otp": "123456"},
                      headers=K), "kamla abha")
    k_sid, k_tok = new_visit(c, kamla["id"], "joint_pain", "घुटनों में दर्द")
    for qid, value in KAMLA_ANSWERS:
        ok(c.post(f"/api/sessions/{k_sid}/answers", json={"question_id": qid, "source": "tap", "value": value},
                  headers=K), f"answer {qid}")
    assert ok(c.get(f"/api/sessions/{k_sid}/next-question", headers=K), "done?")["done"] is True
    add_cbc(k_sid, kamla["id"])
    for item in ok(c.get(f"/api/sessions/{k_sid}/readback?language=hi", headers=K), "readback")["items"]:
        ok(c.post(f"/api/sessions/{k_sid}/readback", json={"fact_id": item["fact_id"], "response": "yes"},
                  headers=K), "readback yes")
    k_sub = ok(c.post(f"/api/sessions/{k_sid}/submit", headers=K), "submit")

    # 2. Rahul Verma — triaged only
    rahul = ok(c.post("/api/patients/abha/verify", json={"abha_number": "98765432109876", "otp": "123456"},
                      headers=K), "rahul abha")
    _, r_tok = new_visit(c, rahul["id"], "fever", "bukhar")

    # 3. Sita Sharma — seen by Dr. Mehta, sent for a recheck (priority, reserved for D1)
    sita = ok(c.post("/api/patients/register", json={"name": "Sita Sharma", "age": 48, "sex": "F", "language": "hi"},
                     headers=K), "sita")
    s_sid, s_tok = new_visit(c, sita["id"], "joint_pain", "kamar dard")
    ok(c.post(f"/api/sessions/{s_sid}/answers", json={"question_id": "jp_site", "source": "tap", "value": "back"},
              headers=K), "sita answer")
    ok(c.post(f"/api/tokens/{s_tok['id']}/in", headers=mehta), "sita in")
    s_tok = ok(c.post(f"/api/tokens/{s_tok['id']}/outcome", headers=mehta,
                      json={"outcome": "recheck", "note": "X-ray lumbar spine, then come back"}), "recheck")

    # island off, empty outbox (fresh tables), audit chain valid
    admin = login("A1", "5555")
    ok(c.post("/api/admin/island", json={"enabled": False}, headers=admin), "island off")
    audit_ok = ok(c.get("/api/admin/audit/verify", headers=admin), "audit")
    outbox = ok(c.get("/api/admin/outbox", headers=admin), "outbox")

    rows = [
        ("Kamla Devi", "ABHA", k_tok["display"], "ayurveda", f"submitted · summary v{k_sub['summary_version']}",
         "normal"),
        ("Rahul Verma", "ABHA", r_tok["display"], "general", "triaged only", "normal"),
        ("Sita Sharma", "new", s_tok["display"], "ayurveda", "recheck for Dr. Mehta", s_tok["lane"]),
    ]
    print(f"\n{'Patient':<13} {'ID':<5} {'Token':<6} {'Department':<10} {'State':<28} Lane")
    for r in rows:
        print(f"{r[0]:<13} {r[1]:<5} {r[2]:<6} {r[3]:<10} {r[4]:<28} {r[5]}")
    print(f"\nisland mode off · outbox {len(outbox)} rows · audit chain valid={audit_ok['valid']} "
          f"({audit_ok['checked']} entries)")
    print("Logins: D1/1111 Dr. Mehta (ayurveda) · D2/2222 Dr. Rao (general) · N1/3333 nurse · K1/4444 desk · "
          "A1/5555 + A2/6666 admins")


if __name__ == "__main__":
    main()
