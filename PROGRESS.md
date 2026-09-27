# MediKiosk — Build Progress

Build top to bottom. `/next` picks the first unchecked task whose **Needs** are all checked.
Tick a task only when its Acceptance checks pass. Run `/clear` between tasks and `/check` at the end of each phase.

## Phase 0 — Foundation
- [x] F1 · Repo skeleton, Postgres and environment — Needs: —
- [x] F2 · Server skeleton — Needs: F1
- [x] F3 · Data models and database — Needs: F2
- [x] F4 · Hash-chained audit log — Needs: F3
- [x] F5 · WebSocket hub — Needs: F2
- [x] F6 · Seed data and staff login — Needs: F3, F4

## Phase 1 — Walking skeleton (typed answers end to end)
- [x] C6 · Data files: drugs, terminology, mock ABHA — Needs: F1
- [x] C1 · Triage config and joint-pain question graph — Needs: F1
- [ ] S1 · Patients: register and mock ABHA — Needs: F6, C6
- [ ] S2 · Sessions and consent — Needs: S1
- [ ] S3 · Triage and token issue — Needs: S2, C1, F5
- [ ] S4 · Queue selector, queue list, display state — Needs: S3
- [ ] S5 · Token actions and outcomes — Needs: S4
- [ ] S6 · Question graph and tap answers — Needs: S3, C1
- [ ] W1 · Web app skeleton — Needs: F1
- [ ] W2 · Staff login and auto-lock — Needs: W1, F6
- [ ] W3 · Doctor queue board — Needs: W2
- [ ] W4 · Patient view layout (fixtures) — Needs: W1
- [ ] W12 · Assisted desk: walk-in registration — Needs: W2, S3
- [ ] A1 · Android project skeleton and settings — Needs: —
- [ ] A2 · Start screen and kiosk scaffold — Needs: A1
- [ ] A3 · Identify: ABHA or new patient — Needs: A2, S1
- [ ] A4 · Informant and consent — Needs: A3, S2
- [ ] A5 · Triage: complaint, body map, red flags → token — Needs: A4, S3
- [ ] A6 · Token screen with QR — Needs: A5
- [ ] A7 · History loop (tap answers) — Needs: A6, S6
- [ ] A13 · Done screen, wipe, inactivity, resume — Needs: A7
  - **Milestone:** a patient can go from kiosk (or help desk) to the doctor's queue by tapping.

## Phase 2 — Voice
- [ ] N1 · NLP service skeleton and speech recognition — Needs: F1
- [ ] C2 · Red-flag rules, lexicon, festivals — Needs: C1
- [ ] N2 · Normalisation: folk terms and time phrases — Needs: N1, C2
- [ ] N3 · Schema-constrained extraction (`/extract`) — Needs: N2
- [ ] N4 · Negation double-check — Needs: N3
- [ ] S7 · Voice answers via NLP — Needs: S6, N3
- [ ] C4 · Render audio prompts — Needs: C1, C2
- [ ] A9 · Audio prompt playback — Needs: A2, C4
- [ ] A8 · Voice answers (hold to talk) — Needs: A7, S7
  - **Milestone:** answers by voice in Hindi.

## Phase 3 — Safety
- [ ] S8 · Red-flag rules engine — Needs: S6, C2
- [ ] S9 · Alerts API and escalation — Needs: S8
- [ ] S10 · Alarm relay service — Needs: F1
- [ ] W9 · Triage / alert station — Needs: W2, S9, S10
- [ ] A12 · Emergency flow and kiosk beacon — Needs: A2, S9, S10
  - **Milestone:** red flags and the emergency button work — even with the API down.

## Phase 4 — Documents
- [ ] C5 · Sample documents for OCR — Needs: F1
- [ ] N5 · OCR and document classification (`/document`) — Needs: N1, C5
- [ ] N6 · Lab value extraction — Needs: N5
- [ ] N7 · Prescription extraction — Needs: N5, C6
- [ ] S11 · Document upload and facts — Needs: S6, S7, N5
- [ ] A10 · Document capture — Needs: A7, S11
- [ ] W6 · Documents panel and source highlight — Needs: W4
  - **Milestone:** old reports become facts with highlighted sources.

## Phase 5 — Summary and doctor review
- [ ] N8 · Grounded summarisation (`/summarize`) — Needs: N3
- [ ] S12 · Summary builder and submit — Needs: S11, N8
- [ ] S13 · Read-back — Needs: S6
- [ ] A11 · Read-back screen and submit — Needs: A10, S13, S12
- [ ] S14 · Verification endpoints — Needs: S12
- [ ] W5 · Wire patient view to the API — Needs: W4, S14
- [ ] W7 · Outcome bar — Needs: W5, S5
  - **Milestone:** the doctor verifies a summary and closes the visit.

## Phase 6 — Integration and AYUSH
- [ ] D1 · Mock HIS — Needs: F1
- [ ] S15 · FHIR bundle builder — Needs: S14, D1
- [ ] S16 · Outbox worker, island mode, admin health — Needs: S15
- [ ] W11 · Admin console — Needs: W2, S16
- [ ] C3 · AYUSH question set — Needs: C1
- [ ] S17 · Terminology search — Needs: F6, C6
- [ ] W8 · AYUSH tab and diagnosis coding — Needs: W5, S17
  - **Milestone:** FHIR to HIS, island mode, AYUSH tab.

## Phase 7 — Security, modes and demo
- [ ] S18 · Per-patient encryption and erasure — Needs: S11, S7
- [ ] S19 · Auth guards everywhere — Needs: S5, S9, S11, S14, S16, S17, S18
- [ ] A14 · Patient app mode (Z Fold) — Needs: A7, S4
- [ ] A15 · Accessibility settings and hall-station mode — Needs: A13
- [ ] W10 · Display board — Needs: W1, S5
- [ ] D2 · Demo reset — Needs: S16
- [ ] D3 · End-to-end smoke test — Needs: S19, S16, D1
- [ ] D4 · Demo script and checklist — Needs: D2
  - **Milestone:** demo-ready.

## Notes for later tasks

<!-- One line per note: `- [ID] note`. Decisions, gotchas, TODOs left for later tasks. -->
- [F1] Docker Postgres is mapped to host port **5433** (not 5432): this Mac's Homebrew postgresql@18 already owns localhost:5432. `DATABASE_URL` in `.env`/`.env.example` uses 5433; inside the container it is still 5432.
- [F1] Python 3.11 comes from `uv python install 3.11` (system python3 is 3.14) — use `uv run`, never bare `python3`, for service code.
- [F2] Server is pinned to Python 3.11 (`server/.python-version`); tests run from `server/` with `pythonpath=["."]` so imports are `from app.x import …`. `ApiError(status, code, message)` in `app/errors.py`; 404s also return the §1 body with code `not_found`.
- [F3] Enum columns are plain strings (compare with `== Lane.emergency` or `"emergency"`, both work). JSON columns are NOT mutation-tracked — reassign (`fact.value = {**fact.value, "k": v}`), never mutate in place.
- [F3] Tests: fixtures `engine` (in-memory SQLite, monkeypatched into `app.db.engine`), `db`, `client` (TestClient with lifespan). Use `app.ids.iso_z()` to serialise datetimes (SQLite returns naive UTC).
- [F4] `audit.record(db, actor, action, entity, entity_id, details)` flushes but does NOT commit — commit it with your change. Postgres uses `pg_advisory_xact_lock` to keep the chain linear. Routes use `db: DbSession` (Annotated dependency in `app/db.py`); put it before params with defaults.
- [F5] `from app.ws import hub`; call `hub.emit(["queue","display"], "token.created", data)` from sync or async code. The `/ws` router is included explicitly in `main.py` (it lives in `app/ws.py`, not `app/routers/`).
- [F6] Auth: `Depends(current_staff(["doctor"]))` → Staff; `Depends(kiosk_id)` → str. Login upper-cases `staff_id`, returns the same `invalid_pin` for unknown id or wrong PIN, and audits failures as `staff.login_failed`. Seed: `cd server && uv run python ../scripts/seed.py`; `seed(db)` is importable for tests (see `tests/test_login.py::_seed`).
- [F6] TODO(S19): 4-digit PINs have no attempt limit yet — consider a per-staff lockout when wiring auth guards (not in the contract; propose it in docs/contract-change-requests.md if needed).
- [C6] `mock_abha.json` has 2 profiles (Kamla Devi 12345678901234, Rahul Verma 98765432109876): §9.7 shows only one, and the card says "two … plus Rahul" — treated as two total. drugs.csv multi-value cells (brands, strengths) are `; `-separated. All terminology codes are `SAMPLE-*` placeholders.
- [C1] joint_pain slots: site, side, duration_days, onset, character, swelling, swelling_where, morning_stiffness, worse_with, better_with, severity (scale_0_10), fever, injury, other_joints, current_medicines (list_string, section drugs), allergy (bool), allergy_detail (string, section allergies). Free questions carry tap-fallback choices (`none`, `not_sure`) — S6 must accept a choice value for free questions (e.g. `current_medicines: []` for `none`, fact flagged unsure for `not_sure`). `jp_duration` has numeric fallback choices (3/14/90/365 days).
