# MediKiosk — Task Cards

Each card is ~20 minutes of Claude Code work plus your review. Run a card with `/task <ID>`, or `/next`
to take the next ready one. Cards follow `CLAUDE.md` and `CONTRACTS.md` — references like §4.3 point there.

Card format: **Needs** (tasks that must be done first) · **Files** (what may be touched) · **Build** · **Acceptance** (how "done" is proven) · **Don't**.
Times exclude one-off downloads (models, Gradle, npm).

---

## F1 · Repo skeleton, Postgres and environment
**Needs:** — · **Files:** folders from CLAUDE.md §5, docker-compose.yml, .env.example, .env, .gitignore, Makefile, README.md, docs/contract-change-requests.md

**Build**
- Create every folder in CLAUDE.md §5 (`.gitkeep` in empty ones). Run `git init` if needed.
- `docker-compose.yml`: one service `postgres` — image `postgres:16`, db `medikiosk`, user `mk`, password `mk`, port 5432, named volume `pgdata`.
- `.env.example` and `.env` with: `DATABASE_URL=postgresql+psycopg://mk:mk@localhost:5432/medikiosk`, `NLP_URL=http://localhost:8001`, `HIS_URL=http://localhost:8002`, `RELAY_URL=http://localhost:8003`, `OLLAMA_URL=http://localhost:11434`, `OLLAMA_MODEL=qwen2.5:3b-instruct-q4_K_M`, `SERVER_PREFIX=A`, `WAIT_LIMIT_MIN=90`, `ESCALATE_AFTER_SEC=60`, `JWT_SECRET=`, `MASTER_KEY_B64=`, `CONTENT_DIR=<abs path>/content`, `DATA_DIR=<abs path>/data`. In `.env` only, fill JWT_SECRET and MASTER_KEY_B64 with fresh random values (32 bytes, base64).
- `.gitignore`: Python, Node, Android/Gradle, `.env`, `data/`, `.venv/`.
- `Makefile` targets: `db-up`, `db-down`, `server`, `nlp`, `relay`, `his`, `web`, `test` (placeholders for services not yet created are fine).
- `README.md`: two-line purpose + run commands from CLAUDE.md §11. `docs/contract-change-requests.md` with a heading.

**Acceptance**
- `docker compose up -d postgres && docker compose exec postgres psql -U mk -d medikiosk -c "select 1"` returns 1.
- `git status` does not list `.env`.

**Don't:** create any application code yet.

## F2 · Server skeleton
**Needs:** F1 · **Files:** server/pyproject.toml, server/app/{main,config,errors}.py, server/app/routers/__init__.py, server/app/services/__init__.py, server/tests/test_health.py, Makefile

**Build**
- `uv init` in `server/`; deps: fastapi, uvicorn[standard], sqlmodel, psycopg[binary], pydantic-settings, pyjwt, httpx, python-multipart, pyyaml, cryptography, rapidfuzz, fhir.resources; dev deps: pytest, respx.
- `config.py`: pydantic-settings `Settings` reading every key from F1's `.env` (repo root).
- `errors.py`: `ApiError(status, code, message)` + handlers returning the §1 error body; `RequestValidationError` → 422 `validation_error`.
- `main.py`: `FastAPI(title="MediKiosk API", version="0.1.0")`, CORS allow all origins, handlers registered, **auto-include** every module in `app/routers/` that exposes `router`, `GET /api/health` (§4.1).
- Makefile `server`: `cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`.

**Acceptance**
- `make server` then `curl localhost:8000/api/health` → `{"status":"ok","version":"0.1.0"}`.
- `cd server && uv run pytest -q` passes.

## F3 · Data models and database
**Needs:** F2 · **Files:** server/app/{enums,ids,models,db}.py, server/tests/{conftest,test_models}.py, server/app/main.py (startup hook only)

**Build**
- `enums.py`: every enum in §2 as `class X(str, Enum)`.
- `ids.py`: `new_id()` (uuid4 str), `utcnow()` (aware UTC), `today_ist()` (date in Asia/Kolkata).
- `models.py`: every table in §3 (SQLModel, `table=True`); JSON via `sa_column=Column(JSON)`; indexes on session.patient_id, token (day, department, status), fact.session_id.
- `db.py`: engine from `DATABASE_URL`, `init_db()` (create_all) on startup, `get_session()` dependency.
- `tests/conftest.py`: SQLite in-memory (StaticPool) override, fixtures `db` and `client`.
- `tests/test_models.py`: insert and read back one row of every table.

**Acceptance**
- Server starts; `docker compose exec postgres psql -U mk -d medikiosk -c "\dt"` lists all 18 tables.
- pytest passes.

## F4 · Hash-chained audit log
**Needs:** F3 · **Files:** server/app/audit.py, server/app/routers/admin_audit.py, server/tests/test_audit.py

**Build**
- `audit.py`: `record(db, actor, action, entity, entity_id, details) -> AuditLog` exactly per §10.7; `verify_chain(db) -> (valid, checked, first_bad_id)`.
- Routes: `GET /api/admin/audit?limit=`, `GET /api/admin/audit/verify` (§4.9). Add `# TODO(S19): admin only` — no auth yet.
- Tests: 3 records → valid; edit row 2's `details` directly in the DB → `valid: false, first_bad_id: 2`.

**Acceptance**
- pytest passes; `curl localhost:8000/api/admin/audit/verify` on an empty DB → `{"valid":true,"checked":0,"first_bad_id":null}`.

## F5 · WebSocket hub
**Needs:** F2 · **Files:** server/app/ws.py, server/tests/test_ws.py

**Build**
- `ws.py`: `Hub` with channels `queue, alerts, display, admin`; `async publish(channel, type, data)` sends `{"type","data","ts"}` (§5); dead sockets dropped; `emit(channels, type, data)` usable from sync code (schedules on the running loop; silent no-op without one); endpoint `/ws?channel=` (unknown channel → close 1008); module-level `hub`.
- Test: connect to `queue` via TestClient websocket, publish through a route defined inside the test, receive the message.

**Acceptance**
- pytest passes.

## F6 · Seed data and staff login
**Needs:** F3, F4 · **Files:** server/app/auth.py, server/app/routers/staff.py, scripts/seed.py, server/tests/test_login.py

**Build**
- `auth.py`: `hash_pin`/`check_pin` (hashlib.pbkdf2_hmac sha256, 100k rounds, random salt, `salt$hash` hex); `create_jwt(staff)` (HS256; claims sub, role, department; 12 h); dependency factory `current_staff(roles: list[str] | None = None)` → Staff, else 401 `unauthorized` / 403 `forbidden`; dependency `kiosk_id()` reading `X-Kiosk-Id` (400 `missing_kiosk_id`).
- `POST /api/staff/login` (§4.1), audited as `staff.login`.
- `scripts/seed.py` (idempotent; run from `server/` with `uv run python ../scripts/seed.py`): staff with **exact ids** D1 Dr. Mehta (doctor, ayurveda, Room 1, PIN 1111), D2 Dr. Rao (doctor, general, Room 2, 2222), N1 Nurse Asha (nurse, 3333), K1 Desk Ravi (desk, 4444), A1 Admin Priya (admin, 5555), A2 Admin Sunil (admin, 6666); setting `island_mode=false`.

**Acceptance**
- Seeding twice creates no duplicates; login D1/1111 returns a token; D1/0000 → 401 `invalid_pin`; pytest passes.

## C6 · Data files: drugs, terminology, mock ABHA
**Needs:** F1 · **Files:** content/drugs.csv, content/terminology.csv, content/mock_abha.json

**Build**
- `drugs.csv` (§9.7): ~60 common Indian OPD generics (e.g. paracetamol, metformin, amlodipine, atorvastatin, pantoprazole, cetirizine) with typical strengths and 1–2 brand examples; ~20 classical Ayurvedic formulations (`system=ayurveda`: Triphala churna, Ashwagandha churna, Yograj guggulu, Dashmool kwath…).
- `terminology.csv` (§9.7): ~25 rows of **placeholder codes only** (`SAMPLE-NAM-001`, `SAMPLE-TM2-001`, `sample=true`) for common conditions (e.g. Sandhigata Vata / knee osteoarthritis). Never invent official-looking codes.
- `mock_abha.json`: exactly the two profiles in §9.7 plus `98765432109876` Rahul Verma, 35, M, en.

**Acceptance**
- `python3 -c "import csv;print(sum(1 for _ in csv.DictReader(open('content/drugs.csv'))))"` ≥ 70; the JSON loads.

## C1 · Triage config and joint-pain question graph
**Needs:** F1 · **Files:** content/triage.yaml, content/questions/joint_pain.yaml, scripts/validate_content.py

**Build**
- `triage.yaml` per §9.2: every complaint code (§2) with icon key and en/hi labels; `joint_pain` → department `ayurveda`, pathway `joint_pain`; all others `general`, pathway `null`; the 5 red-flag questions exactly as in §9.2.
- `joint_pain.yaml` per §9.1, ~15 questions: site (choice), side (left/right/both), duration (duration), onset (sudden/gradual), character (aching/sharp/burning/throbbing), swelling (yesno → branch to swelling_where), morning stiffness (none/<30 min/>30 min), worse with (multi: stairs, walking, cold, rest, morning), better with (multi: rest, heat, movement, medicine), severity (scale), fever (yesno, slot `fever`), injury (yesno), other joints (multi), current medicines (free, list_string, section `drugs`), allergies (yesno → free `allergy_detail`, section `allergies`). Everyday Hindi, no Sanskrit. First line: `# DRAFT — clinician review required`.
- `validate_content.py`: unique ids across all files, `next` targets exist or are `end`, choice/multi have choices, slot and question types and sections valid (§2); non-zero exit on error.

**Acceptance**
- `python3 scripts/validate_content.py` prints `OK`.

## S1 · Patients: register and mock ABHA
**Needs:** F6, C6 · **Files:** server/app/routers/patients.py, server/tests/test_patients.py

**Build**
- Routes per §4.2 using the `kiosk_id` dependency.
- register: name non-empty, age 0–120, enums checked; `hospital_id` = `MK-` + next 6-digit number.
- abha/verify: exactly 14 digits (else 422 `invalid_abha`); OTP `123456` (else 401 `invalid_otp`); lookup per §4.2 using `content/mock_abha.json`.
- Any Aadhaar-like field in the request is ignored and never stored.
- Audit every create (`patient.create`, actor `kiosk:<id>`).

**Acceptance**
- pytest passes: register, sequential ids, ABHA found, ABHA 404, wrong OTP.

## S2 · Sessions and consent
**Needs:** S1 · **Files:** server/app/routers/sessions.py, server/tests/test_sessions.py

**Build**
- `POST /api/sessions`, `GET /api/sessions/{id}`, `POST /api/sessions/{id}/consent` per §4.3; store `kiosk_id` from the header; `legal_basis=consent`; status transitions; audit; unknown id → 404 `not_found`.

**Acceptance**
- pytest passes: create → consent → status `consented`.

## S3 · Triage and token issue
**Needs:** S2, C1, F5 · **Files:** server/app/services/{tokens,serialize,redflags}.py, server/app/routers/triage.py, server/tests/test_triage.py

**Build**
- `tokens.py`: `issue_token(db, session, department, lane="normal", arrival_seq=None, day=None, preferred_doctor_id=None)` per §10.1.
- `serialize.py`: `queue_item(db, token)` → QueueItem §11.2 (wait_min; flags `red_flag` if an open/acknowledged/confirmed alert exists for the session, `aged`, `recheck` if preferred_doctor_id set, `referred`).
- `redflags.py` — **only if the file doesn't exist**: stub `evaluate_and_alert(db, session, slots) -> list` returning `[]` with `# TODO(S8)`.
- `POST /api/sessions/{id}/triage` (§4.3): department + pathway from `content/triage.yaml`; store Answer(`question_id="triage"`, slots = red flags + complaint); Fact(section `complaint`, key `chief_complaint`, text_en = English label, patient_words = complaint_text); issue token; call red-flag check; session → `triaged`; emit `token.created` (queue, display); audit.

**Acceptance**
- pytest passes: first token `A-001`, second `A-002`; joint_pain → ayurveda.

## S4 · Queue selector, queue list, display state
**Needs:** S3 · **Files:** server/app/services/queue.py, server/app/routers/queue.py, server/tests/test_queue.py

**Build**
- `queue.py`: `preview(db, department)` and `select_next(db, department, doctor_id)` exactly per §10.2.
- Routes: `GET /api/queue`, `POST /api/queue/next` (marks called like /call; 204 if empty), `GET /api/display/state` (§11.5: now_serving = last 3 called/in tokens today with doctor name + room; next = first 5 of preview). Auth via `current_staff` as §4.6 says; display is public.

**Acceptance**
- pytest passes: emergency first; aged normal beats priority; priority reserved for another doctor skipped; departments separate; display shape matches §11.5.

## S5 · Token actions and outcomes
**Needs:** S4 · **Files:** server/app/routers/tokens.py, server/tests/test_tokens.py

**Build**
- call, in, no-show, reactivate, outcome, `POST /api/doctors/signout` exactly per §4.6 and §10.3, including `results_tomorrow` and refer rules.
- Emit `token.called` (with doctor_name, room) / `token.updated`; audit every action.
- Outcome `out`: call `services.fhir.enqueue_bundle(db, session)` if that module exists; otherwise `# TODO(S15)`.

**Acceptance**
- pytest passes for every transition in §10.3.

## S6 · Question graph and tap answers
**Needs:** S3, C1 · **Files:** server/app/services/graph.py, server/app/routers/intake.py, server/tests/test_graph.py

**Build**
- `graph.py`: load all `content/questions/*.yaml` at startup; `next_question(db, session)` walks from the pathway start using answered slots and `next` rules (§9.1); department `ayurveda` continues into `ayush.yaml` if it exists; progress = answered + remaining questions on the default path.
- `render(question, language)` → Question §11.4.
- `apply_answer(db, session, question, value, source, raw_text=None, confidence=None, status="confident")`: validate value against slot type, store Answer, create/update Fact (section from question, key = slot name, text_en from a template — choice labels, "Duration: N days", "Severity: 7/10", "Yes: <question text_en>"/"No: …"), then call `redflags.evaluate_and_alert` with **all** slots so far. Keep it importable — S7 reuses it.
- Routes: `GET /api/sessions/{id}/next-question`, `POST /api/sessions/{id}/answers` (§4.3); when done, session → `documents`.
- Tests use a tiny graph defined inside the test, not the content files.

**Acceptance**
- pytest passes; manual curl flow: register → session → consent → triage joint_pain → next-question returns `jp_site` in Hindi.

## W1 · Web app skeleton
**Needs:** F1 · **Files:** web/** (new)

**Build**
- `npm create vite@latest web -- --template react-ts`; add Tailwind and React Router.
- Routes: `/login`, `/doctor`, `/doctor/session/:sessionId`, `/triage`, `/desk`, `/display`, `/admin` (placeholder pages).
- `web/.env.example`: `VITE_API_URL=http://localhost:8000`, `VITE_WS_URL=ws://localhost:8000`, `VITE_RELAY_URL=http://localhost:8003`, `VITE_RELAY_WS=ws://localhost:8003/ws`, `VITE_USE_FIXTURES=false`.
- `src/api/types.ts`: types for every §2 enum and §11 payload (+ Session, Patient, Document, Fact, Outbox, AuditLog from §3).
- `src/api/client.ts`: `api<T>(method, path, body?)` — base `VITE_API_URL` (default http://localhost:8000), JSON, Bearer token from the auth store, throws `ApiError(code, message)` from §1; when `VITE_USE_FIXTURES=true`, GETs come from `src/fixtures/*.json` (summary, queue with 5 items across lanes, alerts, display — built from §11).
- `src/ws/useChannel.ts`: connects to `${VITE_WS_URL}/ws?channel=`, reconnects with backoff, returns `{connected, lastMessage}` and accepts `onMessage`.
- `src/theme.ts`: navy #1F497D, orange #E07B24, green #1E8E6A, red #C0392B; trust chips patient_said blue, from_report orange, doctor_verified green, rejected grey.

**Acceptance**
- `npm run dev` shows all routes; `npx tsc --noEmit` passes.

## W2 · Staff login and auto-lock
**Needs:** W1, F6 · **Files:** web/src/pages/Login.tsx, web/src/auth/**, web/src/App.tsx

**Build**
- `/login`: staff ID field + large 4-digit PIN keypad → `POST /api/staff/login`; auth store (memory + sessionStorage); `RequireRole` wrapper; redirect by role (doctor → /doctor, nurse → /triage, admin → /admin, desk → /desk).
- After 5 min without input, a PIN re-entry overlay for the same staff member (page state kept). Logout in the header.

**Acceptance**
- With server + seed: D1/1111 lands on /doctor; a wrong PIN shows the error; tsc passes.

## W3 · Doctor queue board
**Needs:** W2 · **Files:** web/src/pages/DoctorQueue.tsx, web/src/components/QueueCard.tsx

**Build**
- Three groups (Emergency, Priority, Normal) of QueueItem cards: token, name/age/sex, language, complaint, wait minutes, flag chips (red_flag red, aged amber, recheck orange, referred blue, "with Dr X" grey).
- "Next patient" (`POST /api/queue/next`); per card Call / In / No-show; In → `/doctor/session/:sessionId`.
- Live via `useChannel("queue")` + 10 s poll fallback; department = the doctor's department.

**Acceptance**
- Works on fixtures now and against the live server once S5 exists; tsc passes.

## W4 · Patient view layout (fixtures)
**Needs:** W1 · **Files:** web/src/pages/PatientView.tsx, web/src/components/{PatientHeader,CriticalStrip,SectionAccordion,TrustChip}.tsx

**Build**
- Uses the §11.1 fixture only — no API calls.
- Sticky header: name, age/sex, token, ABHA or "No ABHA", language, informant, complaint, **red allergy banner** if any allergy, red-flag tag.
- Left: critical strip (allergies, red flags, abnormal labs), then sections in §2 display order; each item shows text, trust chip, patient_words in italics, flag chips; HPI narrative on top of its section; drugs with `found_in_documents` grouped under "Found in documents — not yet verified".
- Right: documents list placeholder (pinned first). Bottom: action-bar placeholder.

**Acceptance**
- Renders the fixture faithfully; tsc passes.

## W12 · Assisted desk: walk-in registration
**Needs:** W2, S3 · **Files:** web/src/pages/Desk.tsx, web/src/api/kiosk.ts

**Build**
- `/desk` (role desk): staff register a walk-in in under a minute — name, age, sex, language, complaint (complaint codes §2), the 5 red-flag yes/no questions, informant (self / proxy + relation).
- `kiosk.ts`: calls the kiosk endpoints with header `X-Kiosk-Id: DESK-01` (no Bearer token): register → session → consent (all toggles true, `check_passed: true` — staff explain consent verbally) → triage.
- Show the issued token large with its QR (npm `qrcode`) so the patient can continue the history at a hall station; list today's desk registrations below.

**Acceptance**
- A walk-in registered at /desk appears in the doctor's queue; the QR resumes the session in HALL mode; tsc passes.

## A1 · Android project skeleton and settings
**Needs:** — · **Files:** android/** (new)

**Human step (3 min):** in Android Studio: New Project → Empty Activity (Compose), name `MediKiosk`, package `org.neural.medikiosk`, min SDK 26, location `android/`. Tell Claude when done.

**Build**
- Dependencies: Navigation Compose, Retrofit + kotlinx.serialization converter, OkHttp (+ logging), DataStore Preferences, CameraX (camera2, lifecycle, view), ZXing core, Material icons extended.
- Manifest: INTERNET, RECORD_AUDIO, CAMERA; `android:usesCleartextTraffic="true"` (LAN http).
- `data/Settings.kt` (DataStore): serverUrl, relayUrl, deviceId, deviceMode (§2), defaultLanguage.
- `net/Api.kt`: Retrofit interface for the kiosk endpoints in §4.2–4.5, §4.8 and `/api/health`; interceptor adds `X-Kiosk-Id`; `net/Models.kt`: data classes mirroring §2/§11.
- Hidden settings screen (long-press the logo 3 s) with the fields above and "Test connection" (health → green Connected chip).
- Theme: body 20sp, buttons 24sp, touch targets ≥ 56dp; high-contrast scheme option.

**Acceptance**
- `cd android && ./gradlew assembleDebug` succeeds. Manual: settings persist; Test connection is green with the server running.

## A2 · Start screen and kiosk scaffold
**Needs:** A1 · **Files:** android/app/src/main/java/org/neural/medikiosk/{ui/KioskScaffold.kt, ui/StartScreen.kt, audio/AudioPrompter.kt, IntakeViewModel.kt, navigation}

**Build**
- `KioskScaffold`: used by every intake screen — top bar with a large red **Emergency** button (route `emergency`, placeholder screen until A12) and **Need help** (full-screen "A staff member will come to you" + back).
- `AudioPrompter` interface (`play(key, lang)`, `stop()`) with a no-op implementation (A9 replaces it).
- Start screen: two big tiles (हिंदी / English) → sets language → Identify route; plays `sys_welcome`.
- deviceMode `KIOSK` → `startLockTask()` (note in README how to enable screen pinning).
- `IntakeViewModel` (activity-scoped): language, patient, session, token, with `clear()`.

**Acceptance**
- Builds. Manual: Emergency and Need help visible on Start and navigate.

## A3 · Identify: ABHA or new patient
**Needs:** A2, S1 · **Files:** android/.../ui/IdentifyScreen.kt, res/values/strings.xml, res/values-hi/strings.xml

**Build**
- Choice: "I have ABHA" / "New patient".
- ABHA: 14-digit large numeric keypad → 6-digit OTP keypad → `POST /api/patients/abha/verify`.
- New: name (TextField; system keyboard voice typing allowed), age (numeric keypad), sex (3 icon buttons) → `POST /api/patients/register`.
- Store patient in IntakeViewModel → Informant route. All strings in en + hi; §1 error codes mapped to friendly messages in the chosen language.

**Acceptance**
- Manual: both paths return a patient (check with `curl -H "X-Kiosk-Id: KIOSK-01" localhost:8000/api/patients/<id>`).

## A4 · Informant and consent
**Needs:** A3, S2 · **Files:** android/.../ui/{InformantScreen,ConsentScreen}.kt

**Build**
- Informant: "Myself" / "For someone else" → relation chips (son, daughter, spouse, parent, other) → `POST /api/sessions`.
- Consent: plays `sys_consent`; 4 toggles default ON (capture, scan, share_hospital, link_abha — last one only if the patient has ABHA); check question "Who will see this information?" with 3 picture options (correct: "Your doctor at this hospital"); wrong → replay once; second attempt proceeds with `check_passed=false` → `POST consent` → Triage route.

**Acceptance**
- Manual: session status becomes `consented` (GET the session).

## A5 · Triage: complaint, body map, red flags → token
**Needs:** A4, S3 · **Files:** android/.../ui/TriageScreen.kt, android/.../ui/BodyMap.kt

**Build**
- Complaint grid: all §2 complaint codes with icons + hi/en labels (hard-coded, mirroring content/triage.yaml).
- For joint_pain: simple front/back body outline with tappable regions (knee, hip, shoulder, back, hands) → `body_part`.
- The 5 red-flag questions, one per screen, big ✓ / ✗, audio key = slot name → `POST /api/sessions/{id}/triage`.
- If `alerts` is non-empty, banner "A nurse has been informed" and continue → Token route.

**Acceptance**
- Manual: after triage on the phone, the token appears in `GET /api/queue` (with a doctor token).

## A6 · Token screen with QR
**Needs:** A5 · **Files:** android/.../ui/TokenScreen.kt

**Build**
- Big token (e.g. A-017) + department; QR (ZXing) of `{"session_id","token_id"}` (§10.9).
- Buttons: "Continue your history here" → History; "Continue at a hall station" → large QR + instructions, then Done.
- In PATIENT_APP mode, a status-card placeholder (A14 fills it).

**Acceptance**
- Manual: any QR reader decodes the JSON payload.

## A7 · History loop (tap answers)
**Needs:** A6, S6 · **Files:** android/.../ui/HistoryScreen.kt, android/.../ui/answers/*.kt

**Build**
- Loop: `GET next-question` → render by `type`: choice/multi (icon cards + labels), yesno (✓/✗), number (keypad), duration (keypad + unit chips days/weeks/months/years → days), scale (0–10 faces), free (text field + mic placeholder for A8) → `POST answers` → render `next`.
- Progress bar from `progress`; plays question audio via AudioPrompter (key = `audio`); `done: true` → Documents route (placeholder until A10).

**Acceptance**
- Manual: complete the joint-pain pathway by tapping; facts appear in the DB.

## A13 · Done screen, wipe, inactivity, resume
**Needs:** A7 · **Files:** android/.../ui/{DoneScreen,ResumeScanner}.kt, android/.../InactivityWatcher.kt

**Build**
- Done: "Thank you — please wait for your token to be called" + token; after 10 s → Start, calling `IntakeViewModel.clear()` and deleting cache files (§10.9).
- Inactivity on intake screens: 60 s without touch → `sys_still_there` + 30 s countdown overlay → wipe to Start.
- Start gets "Continue with my token" → CameraX + ZXing scanner → `GET /api/sessions/{id}` → History.

**Acceptance**
- Manual: idling wipes to Start; scanning the token QR resumes at the next unanswered question.

## N1 · NLP service skeleton and speech recognition
**Needs:** F1 · **Files:** nlp/** (new), Makefile (`nlp` target)
*The first run downloads ~2.4 GB — not counted in the 20 minutes.*

**Build**
- `uv init` in `nlp/`; deps: fastapi, uvicorn[standard], python-multipart, torch, torchaudio, transformers, onnx, onnxruntime, httpx, pyyaml, rapidocr-onnxruntime, rapidfuzz, pillow; dev: pytest, respx.
- `app/config.py`: pydantic-settings reading the **repo-root** `.env` (`CONTENT_DIR`, `OLLAMA_URL`, `OLLAMA_MODEL`, optional `ASR_DEVICE`); every later NLP task reads settings from here.
- `app/main.py`: `GET /health` (§6).
- `app/asr.py`: load `ai4bharat/indic-conformer-600m-multilingual` (`AutoModel.from_pretrained(..., trust_remote_code=True)`) in a background thread at startup; device CPU (env `ASR_DEVICE=mps` to try Apple GPU); convert any upload with ffmpeg (subprocess) to 16 kHz mono WAV; transcribe with `model(wav, lang, "ctc")`.
- Confidence heuristic (document it in code): 0 if empty; 0.4 if words-per-second is outside 0.5–5 or the text has no letters of the expected script; else 0.85.
- `POST /asr` per §6 (503 `model_loading` until ready). Makefile `nlp`: port 8001, host 0.0.0.0.

**Acceptance**
- `curl -F audio=@sample.m4a -F language=hi localhost:8001/asr` on a recording of "मेरे घुटने में दर्द है" returns Hindi text.
- Unit test for the confidence heuristic passes.

## C2 · Red-flag rules, lexicon, festivals
**Needs:** C1 · **Files:** content/redflags.yaml, content/lexicon_hi.yaml, content/festivals.yaml, scripts/validate_content.py

**Build**
- `redflags.yaml` (§9.3), header `# DRAFT — clinician review required`: chest_pain + breathless → emergency; stroke_signs → emergency; heavy_bleeding → emergency; fainted → urgent; severity ≥ 9 → urgent; fever + swelling → urgent.
- `lexicon_hi.yaml` (§9.4): ~40 folk terms (Devanagari + romanised), negation cues, number words 1–20 (both scripts), unit words.
- `festivals.yaml`: keys `diwali`, `holi` with `null` dates and a comment that dates must be copied from an official calendar.
- Extend `validate_content.py`: every rule slot exists as a question slot or a triage red-flag slot.

**Acceptance**
- `python3 scripts/validate_content.py` prints `OK`.

## N2 · Normalisation: folk terms and time phrases
**Needs:** N1, C2 · **Files:** nlp/app/normalize.py, nlp/tests/test_normalize.py

**Build**
- `normalize(text, language) -> {"text", "durations":[{"phrase","days"}], "terms":[{"phrase","concept","ambiguous"}]}` using `lexicon_hi.yaml` (`CONTENT_DIR` env).
- Durations: number word or digits + unit word (+ optional se/से/for/since) → days (week 7, month 30, year 365). Relative: कल/kal 1, परसों/parson 2, पिछले हफ्ते/pichhle hafte 7, पिछले महीने/pichhle mahine 30. Festival phrases ("Diwali ke baad") → days since that date only if `festivals.yaml` has it.
- ≥ 15 test cases: Hindi, romanised Hindi, English, mixed.

**Acceptance**
- pytest passes.

## N3 · Schema-constrained extraction (`/extract`)
**Needs:** N2 · **Files:** nlp/app/extract.py, nlp/app/main.py (route), nlp/tests/test_extract.py, scripts/try_extract.py

**Build**
- JSON Schema from request `slots`: string, enum → enum list, bool, number, duration_days → integer, scale_0_10 → integer 0–10, list_enum → array of enum, list_string → array of string; every property nullable.
- Ollama `/api/chat` (`OLLAMA_URL`, `OLLAMA_MODEL`), `format` = the schema, temperature 0. System prompt exactly: *"You extract facts from a patient's answer to one clinical question. Return only JSON that matches the schema. Use null for anything the patient did not say. If the patient denies something (for example 'nahi', 'नहीं', 'no'), set it to false. Never guess, never diagnose, never add fields."* Add 3 few-shot turns (Hindi, romanised Hindi, English).
- Null `duration_days` → fill from `normalize()`.
- `status`: `uncertain` if JSON is invalid after one retry, text is empty, or the negation check flags it (call `negation.check` if the module exists, else `# TODO(N4)`).
- Tests mock Ollama with respx. `scripts/try_extract.py "<text>"` calls the real model for manual checks.

**Acceptance**
- pytest passes; `python3 scripts/try_extract.py "teen mahine se ghutne mein dard hai, bukhar nahi hai"` shows duration 90 and fever false.

## N4 · Negation double-check
**Needs:** N3 · **Files:** nlp/app/negation.py, nlp/app/extract.py (wire-in only), nlp/tests/test_negation.py

**Build**
- `check(text, slots, slot_keywords) -> (slots, notes, uncertain)`: tokenise Devanagari + Latin; for each bool slot set to `true`, if a negation cue (lexicon) is within 3 tokens of any keyword for that slot → set it to null, add a note, `uncertain=True`.
- Default keyword map in code for fever, swelling, injury, chest_pain, breathless, fainted (Hindi, romanised, English).
- Wire into `/extract`. ≥ 10 tests.

**Acceptance**
- pytest passes; "bukhar nahi hai" with model output `fever=true` → `uncertain`.

## S7 · Voice answers via NLP
**Needs:** S6, N3 · **Files:** server/app/services/files.py, server/app/routers/intake.py (audio route), server/tests/test_voice.py

**Build**
- `files.py`: `store_file(patient_id, relpath, data)` / `load_file(patient_id, relpath)` — plain read/write under `DATA_DIR` for now with `# TODO(S18): encrypt`.
- `POST /api/sessions/{id}/answers/audio` (§4.3): store audio at `audio/<session>/<uuid>.<ext>`; call NLP `/asr` (30 s timeout) then `/extract` (30 s) with the question's slot and English text; NLP error → 503 `nlp_unavailable`; extract `uncertain` or ASR confidence < 0.6 → store Answer (status `uncertain`), return the **same** question as `next` plus `fallback_choices`; otherwise `graph.apply_answer(...)` with source `voice`, raw_text, confidence.
- Tests with respx for both paths and the 503 path.

**Acceptance**
- pytest passes.

## C4 · Render audio prompts
**Needs:** C1, C2 · **Files:** scripts/render_audio.py, content/audio/**

**Build**
- Collect texts: every question (`text_hi`, `text_en`), triage red-flag questions (key = slot), and the system phrases in §9.7 (write their hi/en texts in the script).
- Render with macOS `say -v <voice> -o tmp.aiff`, then `ffmpeg -i tmp.aiff -ar 22050 -ac 1 -sample_fmt s16 content/audio/<lang>/<key>.wav`. Voices from env `HI_VOICE` (default `Lekha`) and `EN_VOICE` (default `Rishi`); if missing, print how to list voices: `say -v '?' | grep -E 'hi_IN|en_IN'`.
- Skip unchanged texts via a hash cache (`content/audio/.hashes.json`).

**Acceptance**
- Running it creates a WAV for every key; `afplay content/audio/hi/jp_site.wav` speaks Hindi.

## A9 · Audio prompt playback
**Needs:** A2, C4 · **Files:** android/.../audio/AssetAudioPrompter.kt, android/.../ui/ReplayAudioButton.kt, android/app/build.gradle.kts (copy task)

**Build**
- `AssetAudioPrompter` implements AudioPrompter: plays `assets/audio/<lang>/<key>.wav`; stops on navigation.
- `ReplayAudioButton(key)` composable used by every question screen.
- Setting "Handset mode": ON routes audio to the earpiece (AudioManager `MODE_IN_COMMUNICATION`, speakerphone off) so patients hold the phone to their ear; OFF uses the speaker.
- Gradle task `copyAudio` copies `../content/audio` into `app/src/main/assets/audio` before build.

**Acceptance**
- Manual: questions speak automatically; handset mode switches earpiece/speaker.

## A8 · Voice answers (hold to talk)
**Needs:** A7, S7 · **Files:** android/.../ui/MicButton.kt, android/.../ui/DidYouMeanScreen.kt, android/.../ui/HistoryScreen.kt (wire-in)

**Build**
- Large hold-to-talk mic: MediaRecorder MPEG_4 / AAC, 16 kHz mono, into the cache dir; states Recording → Uploading → Understanding; multipart `POST answers/audio`.
- Non-empty `fallback_choices` → "Did you mean…?" screen (plays `sys_did_you_mean`) listing choices as tap buttons → `POST answers` (tap).
- 503 → "Please tap your answer" and hide the mic for that question. RECORD_AUDIO permission flow. Delete audio files after upload.

**Acceptance**
- Manual: saying "teen mahine se" on the duration question advances; mumbling shows "Did you mean…?".

## S8 · Red-flag rules engine
**Needs:** S6, C2 · **Files:** server/app/services/redflags.py (replace stub), server/tests/test_redflags.py

**Build**
- Load `content/redflags.yaml` at startup; `evaluate(slots) -> list[rule]` per §9.3 (all/any; is, in, gte, lte).
- `evaluate_and_alert(db, session, slots)`: create Alert (source `rule`, level/reason from the rule, rule_id) unless an open/acknowledged alert exists for the same session + rule; emit `alert.created` (alerts, admin); audit.
- Tests use inline YAML.

**Acceptance**
- pytest passes; triage with chest_pain + breathless creates an emergency alert.

## S9 · Alerts API and escalation
**Needs:** S8 · **Files:** server/app/routers/alerts.py, server/app/services/escalation.py, server/tests/test_alerts.py

**Build**
- Routes per §4.8: emergency create (idempotent on `id`), list, ack, resolve with lane effects on the session's latest token.
- Startup background task: every 10 s, alerts still `open` after `ESCALATE_AFTER_SEC` and not escalated → `escalated=true`, emit `alert.updated`. Audit everything.

**Acceptance**
- pytest passes: same id twice → one row; ack; confirmed → lane emergency; downgraded → normal with the same `arrival_seq`.

## S10 · Alarm relay service
**Needs:** F1 · **Files:** relay/main.py, relay/test_relay.py, relay/pyproject.toml, Makefile (`relay` target)

**Build**
- Standalone FastAPI per §7 — no database, no imports from `server/`. In-memory list (max 200), dedupe by `id`, WebSocket broadcast, `GET /alarms`, `GET /health`. `make relay` on 0.0.0.0:8003.
- **CORS allow all origins** — the triage web page (:5173) reads `/alarms` directly from the browser.

**Acceptance**
- pytest passes: same id twice → second `duplicate: true`; a WS client receives exactly one message.

## W9 · Triage / alert station
**Needs:** W2, S9, S10 · **Files:** web/src/pages/Triage.tsx, web/src/components/AlertCard.tsx, web/src/ws/useRelay.ts

**Build**
- Subscribe to `useChannel("alerts")` **and** the relay WS (`VITE_RELAY_WS`, default ws://localhost:8003/ws); initial load `GET /api/alerts` + relay `GET /alarms`; merge by `id` — relay-only alerts get the badge "via relay — server not confirmed".
- Cards (emergency first): kiosk, reason, level, live age timer, escalated badge; buttons On my way (ack), Confirm emergency, Downgrade (hidden for relay-only).
- Repeating Web Audio beep while any alert is open (mute 30 s button); banner when either socket is disconnected.

**Acceptance**
- An emergency (kiosk or curl) makes the page beep and show the card within 2 s; with the API server stopped, relay alarms still appear.

## A12 · Emergency flow and kiosk beacon
**Needs:** A2, S9, S10 · **Files:** android/.../ui/EmergencyScreen.kt, android/.../emergency/Beacon.kt

**Build**
- Route `emergency` (replaces the placeholder): big icon grid of reason codes (§2) with hi/en labels.
- On tap: new UUID; send `POST /api/alerts/emergency` and relay `POST /alarm` **in parallel** (3 s timeouts, failures ignored).
- Full-screen "Help is coming — please stay here" (`sys_help_coming`).
- Beacon: screen flashing red/white at 1 Hz, loud tone at alarm volume (ToneGenerator or AudioTrack), torch blinking (CameraManager). Stops when a staff member long-presses "Staff" for 3 s, or when `alert.updated` for this id arrives on the server's alerts channel. Works with or without a session.

**Acceptance**
- Manual: with the API server stopped, the button still triggers the beacon and the relay alarm shows on /triage.

## C5 · Sample documents for OCR
**Needs:** F1 · **Files:** scripts/make_samples.py, content/samples/*.png

**Build**
- Pillow script writing: `lab_report_cbc.png` (Haemoglobin 10.2 g/dL ref 12.0–15.0, WBC, platelets; dated 12/08/2026), `lab_report_diabetes.png` (FBS, HbA1c with ranges), `rx_allopathic.png` (Tab Metformin 500 mg BD x 30 days; Tab Amlodipine 5 mg OD), `rx_ayurveda.png` (Yograj Guggulu 2 tab BD after food; Dashmool Kwath 20 ml BD), `discharge_summary.png`, `handwritten_style.png` (script-like font), plus photographed-look variants (slight rotation, blur, shadow) of two of them.
- Every image stamped "SAMPLE — NOT A REAL REPORT"; fake names; fonts from `/System/Library/Fonts` or `/Library/Fonts`, falling back to Pillow's default.

**Acceptance**
- All files exist, open, and are legible.

## N5 · OCR and document classification (`/document`)
**Needs:** N1, C5 · **Files:** nlp/app/document.py, nlp/app/main.py (route), nlp/tests/test_document.py

**Build**
- RapidOCR → lines `{text, bbox:[x,y,w,h], conf}`.
- doc_type by keyword score — lab: hb, haemoglobin, mg/dl, g/dl, reference, range, test; prescription: rx, tab, cap, syp, od, bd, tds, sos; discharge_summary: discharge, admitted, diagnosis, summary.
- doc_date: first of dd/mm/yyyy, dd-mm-yy, "12 Aug 2026".
- `entities` = `labs.extract(lines)` + `rx.extract(lines)` if those modules exist, else `[]`.
- Tests use `content/samples` (skip if missing).

**Acceptance**
- `curl -F image=@content/samples/lab_report_cbc.png localhost:8001/document` → `lab_report`, date `2026-08-12`, lines present.

## N6 · Lab value extraction
**Needs:** N5 · **Files:** nlp/app/labs.py, nlp/tests/test_labs.py

**Build**
- `extract(lines) -> list[Entity]`: rows "test value unit range" (ranges "12.0 - 15.0", "12.0–15.0", "(12-15)", "< 5.7"); normalise test names (hb/hgb/haemoglobin → Haemoglobin; fbs/fasting glucose; hba1c; tsh; creatinine; total cholesterol; ldl; hdl; triglycerides; wbc; platelets).
- flag low/high/normal only when a range was parsed, else `unknown`; conf = min OCR conf in the row; `readable=false` when conf < 0.6; text_en like "Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW".

**Acceptance**
- pytest passes; the CBC sample yields Haemoglobin LOW.

## N7 · Prescription extraction
**Needs:** N5, C6 · **Files:** nlp/app/rx.py, nlp/tests/test_rx.py

**Build**
- Drug lines: prefix Tab/Tab./Cap/Syp/Inj, or rapidfuzz ≥ 85 against `content/drugs.csv` (generic + brand examples).
- Dose regex (mg, mcg, g, ml, tab); frequency: OD once daily, BD twice daily, TDS three times daily, QID four times daily, HS at bedtime, SOS when needed, AC before food, PC after food; duration ("x 5 days", "for 1 month").
- Value per the §3 drugs shape with `found_in_documents: true`; `readable=false` if conf < 0.6 or prefix matched but no drug.

**Acceptance**
- pytest passes; `rx_allopathic.png` → Metformin 500 mg, twice daily, 30 days.

## S11 · Document upload and facts
**Needs:** S6, S7, N5 · **Files:** server/app/routers/documents.py, server/tests/test_documents.py

**Build**
- Routes per §4.4: validate type and size; store via `files.store_file` at `docs/<doc_id>.bin`; Document `pending`.
- Background task: NLP `/document` (60 s timeout) → save ocr_json, doc_type, doc_date, status `processed` (or `failed`); facts from entities — lab → `labs`, drug → `drugs`, diagnosis → `pmh`; trust `from_report`, source_type `document`, source_id, bbox; unreadable → text_en "Unreadable — see image" + flag; `pinned` = discharge_summary or any abnormal lab; emit `document.processed`; audit.
- `GET /api/documents/{id}` and `/image` (`# TODO(S19)` for auth).

**Acceptance**
- pytest passes (respx mocks NLP).

## A10 · Document capture
**Needs:** A7, S11 · **Files:** android/.../ui/DocumentsScreen.kt

**Build**
- After history: CameraX preview with a document-frame overlay; capture; thumbnail strip with delete/retake; "Add another page"; upload each page (multipart, `page_no`) with progress; "I have no papers" skip → Read-back route (placeholder until A11). Delete local images after upload.

**Acceptance**
- Manual: photographing a printed sample creates processed documents and lab/drug facts on the server.

## W6 · Documents panel and source highlight
**Needs:** W4 · **Files:** web/src/components/{DocumentsPanel,DocumentViewer}.tsx

**Build**
- Thumbnails (fetch `/image` with the Bearer token → object URL), pinned first then by doc_date desc, status badge.
- Click → modal viewer with zoom/pan. Clicking a fact that has `source.bbox` opens its document with a highlight rectangle scaled to the displayed image. Works on fixtures (placeholder image).

**Acceptance**
- tsc passes; the highlight lands on the fixture bbox.

## N8 · Grounded summarisation (`/summarize`)
**Needs:** N3 · **Files:** nlp/app/summarize.py, nlp/app/main.py (route), nlp/tests/test_summarize.py

**Build**
- Ollama, temperature 0: at most 3 sentences of an English history of present illness using ONLY the given facts ("Do not add facts, diagnoses or advice").
- Faithfulness check: a sentence is unsupported if it has a number absent from all fact values/text, or a clinical word (small list + lexicon concepts) absent from the facts → drop it and add to `unsupported_terms`. Nothing left → join fact text_en with "; ", `fallback_used: true`.

**Acceptance**
- pytest passes, including a mocked hallucinated sentence being removed.

## S12 · Summary builder and submit
**Needs:** S11, N8 · **Files:** server/app/services/summary.py, server/app/routers/summary.py, server/tests/test_summary.py

**Build**
- `build(db, session) -> dict` producing exactly §11.1 per §10.5: header, critical strip (allergies always; red flags from alerts not downgraded; abnormal labs), sections in display order (no rejected facts; flags from fact values), HPI narrative via NLP `/summarize` with fallback, documents, `new_since_opened`; carried facts (§10.4) copied in once per session on the first build.
- Store a new Summary version only when content changed.
- `POST /api/sessions/{id}/submit` (§4.5) → build + emit `summary.ready`. `GET /api/sessions/{id}/summary` (§4.7) → rebuild if facts changed; first doctor call sets `opened_by_doctor_at` and status `with_doctor`.

**Acceptance**
- pytest passes; the response has every §11.1 key.

## S13 · Read-back
**Needs:** S6 · **Files:** content/readback_templates.yaml, server/app/routers/readback.py, server/tests/test_readback.py

**Build**
- Templates (§9.6) for every joint-pain slot in hi and en.
- `GET /api/sessions/{id}/readback`: only `patient_said` facts in sections complaint and hpi — never drugs, doses or labs; text from templates, fallback text_en.
- `POST readback`: store Readback; `no` → `value.patient_disputed = true`; `not_sure` → `value.patient_unsure = true`; audit.

**Acceptance**
- pytest passes.

## A11 · Read-back screen and submit
**Needs:** A10, S13, S12 · **Files:** android/.../ui/ReadbackScreen.kt

**Build**
- Plays `sys_readback_intro`; each item as big text, spoken with Android TextToSpeech (hi-IN / en-IN; if unavailable, text only); buttons Yes / No / Not sure → `POST readback`; after the last item `POST submit` → Done.

**Acceptance**
- Manual: the full kiosk journey ends at Done, and the doctor sees the patient with a summary.

## S14 · Verification endpoints
**Needs:** S12 · **Files:** server/app/routers/review.py, server/tests/test_review.py

**Build**
- Per §4.7: section open (SectionView); approve (409 `section_not_opened` unless this doctor opened it; all non-rejected facts in the section → `doctor_verified` with verified_by/at; SectionApproval); fact verify approve/edit/reject; ayush-exam (section `ayush`, source_type `doctor`, trust `doctor_verified`; Pramana computes BMI into text_en); diagnosis.
- Each change is audited and emits `summary.ready` after a rebuild.

**Acceptance**
- pytest passes.

## W5 · Wire patient view to the API
**Needs:** W4, S14 · **Files:** web/src/pages/PatientView.tsx, web/src/components/{SectionAccordion,FactMenu,NewSinceBanner}.tsx

**Build**
- Load `GET /api/sessions/{id}/summary`; opening a section → `POST open`; "Approve section" disabled until opened; per-item menu Approve / Edit (inline) / Reject → `POST /api/facts/{id}/verify`; re-fetch on `summary.ready` for this session; "New since you opened" banner with dismiss; allergy banner always visible.

**Acceptance**
- On the live server, approving a section turns its chips green; tsc passes.

## W7 · Outcome bar
**Needs:** W5, S5 · **Files:** web/src/components/OutcomeBar.tsx

**Build**
- Buttons Out, Recheck (note + "results come tomorrow" checkbox), Refer (department + note), Follow-up (date + admit checkbox); confirm dialog → `POST /api/tokens/{id}/outcome` → back to /doctor.

**Acceptance**
- Each outcome causes the §10.3 queue changes on the live server.

## D1 · Mock HIS
**Needs:** F1 · **Files:** mock_his/main.py, mock_his/test_his.py, mock_his/pyproject.toml, Makefile (`his` target)

**Build**
- Standalone FastAPI per §8: `Idempotency-Key` required (400 otherwise); bundles kept in memory and as JSON under `data/his/`; duplicate key → `duplicate: true`, not stored twice; `GET /bundles`; `GET /` HTML list (time, patient name from the Patient resource, resource counts, expandable raw JSON). `make his` on :8002.

**Acceptance**
- pytest passes; a posted sample bundle shows on the HTML page.

## S15 · FHIR bundle builder
**Needs:** S14, D1 · **Files:** server/app/services/fhir.py, server/app/routers/tokens.py (replace TODO only), server/tests/test_fhir.py

**Build**
- Check the installed `fhir.resources` version first: from v7 the default models are R5 — import the R4B models (`from fhir.resources.R4B.bundle import Bundle`, etc.), which match ABDM's R4 for these resources. Never mix R5 and R4B classes.
- `build_bundle(db, session) -> dict` (type `collection`): Patient (identifiers: hospital_id, ABHA if any), Encounter, Condition (complaint + diagnosis codes), AllergyIntolerance, MedicationStatement, Observation (labs with referenceRange and interpretation), QuestionnaireResponse (answers), Composition (sections + narrative). Every resource gets a `meta.tag` with its trust label; rejected facts excluded.
- `enqueue_bundle(db, session)` → Outbox row (idempotency key per §10.6); wire into outcome `out` (replace S5's TODO).

**Acceptance**
- pytest passes; the bundle parses back with fhir.resources.

## S16 · Outbox worker, island mode, admin health
**Needs:** S15 · **Files:** server/app/services/outbox.py, server/app/routers/admin.py, server/tests/test_outbox.py

**Build**
- Background loop every 5 s exactly per §10.6.
- Routes (§4.9): island GET/POST (emit `island.changed`, audit), outbox GET, admin health (db; NLP `/health`; relay `/health`; HIS `/bundles`; Ollama `/api/tags`; 2 s timeouts).

**Acceptance**
- pytest passes (respx): sent; HIS down → retries with backoff; island on → nothing sent; consent revoked → `skipped_no_consent`; a repeat delivery is harmless.

## W11 · Admin console
**Needs:** W2, S16 · **Files:** web/src/pages/Admin.tsx

**Build**
- Large island-mode toggle with confirm ("In the real deployment only the physical key reconnects"); health tiles (10 s refresh); outbox table with status chips and attempts; audit table (latest 100) with "Verify chain" → valid ✓ or broken at id N; erase-patient form (patient id + second admin id + PIN).

**Acceptance**
- tsc passes; the island toggle reflects server state live.

## C3 · AYUSH question set
**Needs:** C1 · **Files:** content/questions/ayush.yaml

**Build**
- Per §9.5, patient-reportable items only: appetite and quantity (ahara_shakti), exercise tolerance (vyayama_shakti), foods/climate that suit or upset (satmya, multi), digestion — gas, acidity, heaviness after meals (agni), bowel frequency and consistency (koshtha), meal regularity, diet type, spicy/oily frequency, sleep hours, day sleep (ahara_vihara), triggers (nidana, multi), plus a 6-item Prakriti mini-questionnaire (frame, skin, appetite, sleep, temperament, weather preference).
- Everyday Hindi; Sanskrit only in `doctor_note`. Header: `# DRAFT — clinician review required; align Prakriti items with the Ministry of Ayush Prakriti Parikshan tool`.
- Then run `validate_content.py` and `render_audio.py`.

**Acceptance**
- validate_content prints OK; an ayurveda session continues into AYUSH questions after the joint-pain pathway.

## S17 · Terminology search
**Needs:** F6, C6 · **Files:** server/app/services/terminology.py, server/app/routers/terminology.py, server/tests/test_terminology.py

**Build**
- Load `content/terminology.csv` at startup; `GET /api/terminology/search` (§4.10): rapidfuzz WRatio over display + code, top 10 with score ≥ 60, optional system filter, `sample` as bool.

**Acceptance**
- pytest passes.

## W8 · AYUSH tab and diagnosis coding
**Needs:** W5, S17 · **Files:** web/src/components/{AyushTab,DiagnosisBox}.tsx

**Build**
- Tab (department ayurveda only): read-only patient-reported AYUSH facts with trust chips and doctor_note labels.
- Exam form: Nadi (vata/pitta/kapha/mixed + note), Jihva (clean/coated + note), Pramana (height, weight → live BMI), Sara and Samhanana (pravara/madhyama/avara), Vikriti (dosha + note) → `POST ayush-exam`. Label option lists "clinician to confirm".
- Diagnosis box: debounced terminology search (system filter NAMASTE / ICD11_TM2) → chips → `POST diagnosis`; "SAMPLE code" badge when `sample=true`.

**Acceptance**
- Saved exam fields appear as doctor-verified facts in the summary.

## S18 · Per-patient encryption and erasure
**Needs:** S11, S7 · **Files:** server/app/services/crypto.py, server/app/services/files.py, server/app/routers/admin.py (erase route), server/tests/test_crypto.py

**Build**
- `crypto.py` per §10.8 (AES-GCM, master key from `MASTER_KEY_B64`, lazy per-patient key in `patient_key`).
- `files.py`: `store_file`/`load_file` now encrypt/decrypt (replace `TODO(S18)`); erased patient → 410 `patient_erased`.
- `POST /api/admin/patients/{id}/erase` (§4.9): caller admin + a **different** admin's id and PIN → destroy the key; audit.

**Acceptance**
- pytest passes: round-trip; after erase → 410; same approver as caller → 403. Files under `data/` are no longer viewable images.

## S19 · Auth guards everywhere
**Needs:** S5, S9, S11, S14, S16, S17, S18 · **Files:** server/app/routers/*.py, server/tests/conftest.py

**Build**
- Apply every §4 auth marker: K routes require `X-Kiosk-Id`; S routes use `current_staff` with the listed roles; `/api/health` and `/api/display/state` stay public. Resolve every `TODO(S19)`.
- Add test fixtures `kiosk_headers` and `staff_headers(role)`; update existing tests.

**Acceptance**
- Full `uv run pytest` passes; `curl localhost:8000/api/queue` without a token → 401.

## A14 · Patient app mode (Z Fold)
**Needs:** A7, S4 · **Files:** android/.../ui/patientapp/*.kt

**Build**
- deviceMode `PATIENT_APP`: Home "Check in at hospital" (scan a QR containing `{"hospital":"DEMO"}` or tap "Demo check-in") → reuse Identify → Informant/Consent → Triage → Token screen with a live status card (poll `GET /api/display/state?department=` every 15 s: now serving, your place in `next`) → History (reuse A7/A8).
- Two-pane layout when unfolded (status left, question right) using the window size class.

**Acceptance**
- Manual: the Z Fold completes check-in and shows its token moving up as the doctor calls patients.

## A15 · Accessibility settings and hall-station mode
**Needs:** A13 · **Files:** android/.../ui/SettingsScreen.kt, android/.../ui/HallStartScreen.kt

**Build**
- Toggles: large text (font scale ×1.3), high-contrast theme, slower prompts (playback speed 0.85).
- deviceMode `HALL`: Start shows only "Scan your token slip" → resume (A13) → History → Read-back → Done (no documents); auto-wipe after each patient.

**Acceptance**
- Manual: in HALL mode the second phone resumes a kiosk session and finishes it.

## W10 · Display board
**Needs:** W1, S5 · **Files:** web/src/pages/Display.tsx

**Build**
- Public full-screen page: huge "Now serving" tokens with doctor and room, next 5 below; data from `GET /api/display/state` (department picker stored in localStorage) + `useChannel("display")`.
- On `token.called`: chime + `speechSynthesis` in Hindi (hi-IN voice if present) then English — "Token A-017, Dr. Mehta, Room 1". A "Click to enable sound" overlay first (browser autoplay rule).

**Acceptance**
- Calling a patient from /doctor updates the board and speaks within 2 s.

## D2 · Demo reset
**Needs:** S16 · **Files:** scripts/reset_demo.py, Makefile (`demo-reset`)

**Build**
- Drop and recreate all tables, run the seed, then create: Kamla Devi (ayurveda, joint pain, complete history, CBC lab facts inserted directly as `from_report`), Rahul Verma (general, fever, triaged only), one priority recheck token for Dr. Mehta; island off; empty outbox. Print a summary table.

**Acceptance**
- After `make demo-reset`, the doctor board shows the three patients correctly.

## D3 · End-to-end smoke test
**Needs:** S19, S16, D1 · **Files:** scripts/smoke.py

**Build**
- httpx script against live services, printing PASS/FAIL and timing per step: health → register → session → consent → triage → answer every question by tap (first choice / sensible defaults) → upload `lab_report_cbc.png` (skip if NLP down) → read-back yes → submit → login D1 → queue next → in → open and approve all sections → outcome out → poll outbox until `sent` (≤ 20 s) → mock HIS lists the bundle → audit verify valid. Exit code 1 on any failure.

**Acceptance**
- With every service running, all steps PASS.

## D4 · Demo script and checklist
**Needs:** D2 · **Files:** docs/demo-script.md

**Build**
- A 6-minute live demo: cast (kiosk operator, "patient", doctor, narrator), device setup, exact taps and lines to say.
- Beats: Hindi intake on the kiosk; red-flag emergency on the second phone; doctor verifies the summary; unplug the internet (island mode) — everything keeps working; stop the API server — the emergency alarm still reaches triage via the relay; restart — the outbox drains to the HIS.
- Pre-demo checklist (hotspot on, phone IPs set, all make targets up, demo reset run, volumes up, phones charged, screen pinning on) and a recovery plan (backup video, tap fallback, typed answers).

**Acceptance**
- A teammate who has never seen the app can run the demo from this document alone.
