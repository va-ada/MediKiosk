"""Mock hospital information system (CONTRACTS §8) — tiny standalone service, no database.

Receives FHIR R4 Bundles from the server's outbox. Bundles are kept in memory and written as
JSON files under `<repo>/data/his/` (reloaded on start), deduplicated by `Idempotency-Key`.
`GET /` is a small human-readable page for the demo; all bundle content is escaped (untrusted).
"""

import json
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from html import escape
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data" / "his"

# idempotency_key -> {id, idempotency_key, received_at, bundle}; insertion order = arrival order
bundles: dict[str, dict[str, Any]] = {}


class Received(BaseModel):
    received: bool
    id: str
    duplicate: bool


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def load_from_disk() -> None:
    bundles.clear()
    if not DATA_DIR.is_dir():
        return
    records = []
    for path in DATA_DIR.glob("*.json"):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue  # skip unreadable files rather than refusing to start
        if isinstance(rec, dict) and {"id", "idempotency_key", "received_at", "bundle"} <= rec.keys():
            records.append(rec)
    for rec in sorted(records, key=lambda r: r["received_at"]):
        bundles[rec["idempotency_key"]] = rec


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_from_disk()
    yield


app = FastAPI(title="MediKiosk mock HIS", version="0.1.0", lifespan=lifespan)


@app.post("/fhir", response_model=Received)
async def receive_fhir(
    request: Request, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")
) -> Received | JSONResponse:
    if not idempotency_key or not idempotency_key.strip():
        return error(400, "missing_idempotency_key", "Idempotency-Key header is required")
    if idempotency_key in bundles:
        return Received(received=True, id=bundles[idempotency_key]["id"], duplicate=True)
    try:
        bundle = await request.json()
    except (JSONDecodeError, UnicodeDecodeError):
        return error(400, "invalid_json", "Body must be JSON")
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return error(400, "invalid_bundle", "Body must be a FHIR Bundle (resourceType 'Bundle')")

    rec = {
        "id": str(uuid.uuid4()),
        "idempotency_key": idempotency_key,
        "received_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bundle": bundle,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"{rec['id']}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    bundles[idempotency_key] = rec
    return Received(received=True, id=rec["id"], duplicate=False)


@app.get("/bundles")
def list_bundles(limit: int = 100) -> list[dict[str, Any]]:
    """Received bundles, newest first."""
    return list(reversed(bundles.values()))[:limit]


def resources(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    entries = bundle.get("entry")
    if not isinstance(entries, list):
        return []
    return [e["resource"] for e in entries if isinstance(e, dict) and isinstance(e.get("resource"), dict)]


def patient_name(bundle: dict[str, Any]) -> str:
    for res in resources(bundle):
        if res.get("resourceType") != "Patient":
            continue
        names = res.get("name")
        if not isinstance(names, list) or not names or not isinstance(names[0], dict):
            return "(unnamed patient)"
        n = names[0]
        if n.get("text"):
            return str(n["text"])
        given = n.get("given") if isinstance(n.get("given"), list) else []
        parts = [str(g) for g in given] + ([str(n["family"])] if n.get("family") else [])
        return " ".join(parts) or "(unnamed patient)"
    return "(no Patient resource)"


def resource_counts(bundle: dict[str, Any]) -> str:
    counts = Counter(str(r.get("resourceType", "?")) for r in resources(bundle))
    return ", ".join(f"{k} × {v}" for k, v in sorted(counts.items())) or "no resources"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    rows = []
    for rec in reversed(bundles.values()):
        b = rec["bundle"]
        raw = json.dumps(b, ensure_ascii=False, indent=2)
        rows.append(
            "<tr>"
            f"<td>{escape(rec['received_at'])}</td>"
            f"<td>{escape(patient_name(b))}</td>"
            f"<td>{escape(resource_counts(b))}</td>"
            f"<td><code>{escape(rec['idempotency_key'])}</code></td>"
            f"<td><details><summary>raw JSON</summary><pre>{escape(raw)}</pre></details></td>"
            "</tr>"
        )
    body = "".join(rows) or '<tr><td colspan="5">No bundles received yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta http-equiv="refresh" content="5">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mock HIS — received FHIR bundles</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#fff;color:#111}}
table{{border-collapse:collapse;width:100%}} th,td{{border:1px solid #ccc;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f0f0f0}} pre{{max-height:400px;overflow:auto;background:#f7f7f7;padding:8px;font-size:12px}}
</style></head><body>
<h1>Mock HIS</h1><p>{len(bundles)} bundle(s) received. Refreshes every 5 s.</p>
<table><thead><tr><th>Received (UTC)</th><th>Patient</th><th>Resources</th><th>Idempotency-Key</th><th>Bundle</th></tr>
</thead><tbody>{body}</tbody></table></body></html>"""
