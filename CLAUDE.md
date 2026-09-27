# MediKiosk — Project Context for Claude Code

> This file is loaded automatically at the start of every Claude Code session.
> `CONTRACTS.md` (imported below) is the single source of truth for every endpoint, field, enum and file format.
> If a task seems to need something that isn't in `CONTRACTS.md`, do **not** invent it —
> write the proposal in `docs/contract-change-requests.md` and stop.

@CONTRACTS.md

## 0. How we work (Claude Code workflow)

- Work is split into 20-minute task cards in `TASKS.md`. **Never** read all of `TASKS.md` into context —
  read only the card you are working on (from its `## <ID>` heading to the next `## ` heading).
- `PROGRESS.md` is the build log: the ordered task list with checkboxes, plus short notes for later tasks.
  Read it at the start of every task; update it at the end.
- Commands: `/next` (do the next ready task), `/task <ID>` (do a specific task), `/check` (run all tests),
  `/status` (show progress). Their instructions live in `.claude/commands/`.
- One task per context: the user runs `/clear` between tasks. Everything you need to know must
  therefore be in these files, the code, or `PROGRESS.md` notes — never only in chat.
- If a card contains a **Human step**, stop and tell the user exactly what to do, then wait.
- Touch only the files the card names (plus `PROGRESS.md`). Do not refactor other code.

---

## 1. What we are building

MediKiosk is an **offline-first AI patient case-taking platform** for Indian hospital OPDs
(Smart India Hackathon 2026, problem SIH26047, set by the All India Institute of Ayurveda, Ministry of Ayush).

- **Problem:** OPD consultations last 2–5 minutes. There is no time to take a proper history, and
  patients' old paper reports go unread.
- **Solution:** patients give their history **before** the consultation — by **voice or touch**, in
  **Hindi or English** — at a kiosk or on a phone. Old reports are photographed and read by OCR.
  The doctor opens a **structured, trust-labelled summary** and verifies it in one tap.
- **Ayurveda mode:** for Ayurveda OPDs, patient-reportable Dashavidha Pariksha items are asked in
  plain words; examination fields wait for the doctor.

## 2. The patient journey (every feature serves this flow)

| # | Step | Where | Notes |
|---|---|---|---|
| 1 | Identify | Kiosk | ABHA number + OTP (mocked) **or** register as new. Never blocked. |
| 2 | Who is answering + consent | Kiosk | Self or proxy; audio-explained consent with toggles + one check question |
| 3 | Triage (~2 min) | Kiosk | Main complaint (icons/body map/voice) + 5 universal red-flag yes/no questions → **token issued** |
| 4 | Deep history | Kiosk or hall station | Adaptive question graph; every question answerable by voice **or** tap |
| 5 | Documents | Kiosk | Phone camera captures old reports → OCR → facts |
| 6 | Read-back | Kiosk | Patient confirms only what they can judge: yes / no / not sure |
| 7 | Summary | Server | Templates + grounded LLM narrative; every fact trust-labelled |
| 8 | Queue | Server | Emergency > priority > normal, with aging, per department |
| 9 | Consult | Doctor terminal | Open each section, approve/edit/reject; AYUSH exam tab |
| 10 | Outcome | Doctor terminal | Out / Recheck / Refer / Follow-up |
| 11 | Sync | Server | FHIR bundle → mock HIS via outbox (not in island mode) |
| 12 | Wipe | Kiosk | Kiosk keeps no patient data after a session |

**Emergency button on every kiosk screen.** Alarm goes to the server **and** directly to the alarm relay,
and the kiosk itself flashes and sounds (works even if the API server is down).

## 3. Devices and services (demo setup)

| Device | Role | Runs |
|---|---|---|
| MacBook Pro M1 | "Hospital server" + Wi-Fi hotspot (= hospital LAN) | server :8000, nlp :8001, mock HIS :8002, alarm relay :8003, web :5173, Postgres :5432, Ollama :11434 |
| Android phone | Kiosk (device mode `KIOSK`) — also hall station (`HALL`) | Android app |
| Samsung Z Fold 7 | Patient app (device mode `PATIENT_APP`) | Same Android app |
| Mac browser | Doctor terminal, triage station, assisted desk, display board, admin | Web app routes |

## 4. Tech stack (do not substitute without team approval)

| Part | Choice |
|---|---|
| API server | Python 3.11, FastAPI, Uvicorn, SQLModel, PostgreSQL 16 (Docker), httpx, PyJWT, cryptography, PyYAML, rapidfuzz, fhir.resources |
| NLP service | Python 3.11, FastAPI; **ASR:** `ai4bharat/indic-conformer-600m-multilingual` (transformers, trust_remote_code); **LLM:** Ollama `qwen2.5:3b-instruct-q4_K_M` with JSON-schema structured output, temperature 0; **OCR:** RapidOCR (`rapidocr-onnxruntime`); ffmpeg for audio conversion |
| Alarm relay, mock HIS | Tiny standalone FastAPI apps, no database |
| Web | React 18 + TypeScript (strict) + Vite + Tailwind CSS + React Router |
| Android | Kotlin, Jetpack Compose (Material 3), Navigation Compose, Retrofit + kotlinx.serialization, OkHttp WebSocket, CameraX, MediaRecorder, DataStore, ZXing for QR |
| Python env | `uv` |
| Tests | pytest (+ respx for HTTP mocks); web: `tsc --noEmit`; Android: builds + manual check |

## 5. Repo layout

```
medikiosk/
  CLAUDE.md  CONTRACTS.md  TASKS.md  PROGRESS.md  README.md  Makefile  docker-compose.yml  .env.example
  .claude/           commands/ (next, task, check, status)  settings.json
  server/            FastAPI API (:8000)
    app/  main.py config.py db.py models.py enums.py errors.py ids.py auth.py audit.py ws.py
          routers/   one file per area (patients.py, sessions.py, queue.py, ...)
          services/  business logic (queue.py, graph.py, redflags.py, summary.py, fhir.py, outbox.py, crypto.py, ...)
    tests/
  nlp/               NLP service (:8001)   app/ main.py asr.py normalize.py extract.py negation.py document.py labs.py rx.py summarize.py
  relay/             Alarm relay (:8003)   main.py
  mock_his/          Mock hospital information system (:8002)   main.py
  web/               React app             src/ api/ ws/ pages/ components/ fixtures/
  android/           Android app           package org.neural.medikiosk
  content/           questions/*.yaml  triage.yaml  redflags.yaml  lexicon_hi.yaml  festivals.yaml
                     readback_templates.yaml  drugs.csv  terminology.csv  mock_abha.json  audio/{hi,en}/*.wav  samples/
  scripts/           seed.py reset_demo.py render_audio.py make_samples.py validate_content.py smoke.py
  data/              runtime files (gitignored): encrypted documents/audio, HIS inbox
  docs/              demo-script.md, contract-change-requests.md
```

## 6. Non-negotiable product rules

1. **The AI never diagnoses, prescribes, or tells a patient they are fine.**
2. **Questions come only from `content/questions/*.yaml`.** The LLM understands answers; it never invents questions.
3. **Red flags are decided by rules** in `content/redflags.yaml`, never by a model.
4. **Allergies, medicines, red flags and lab values are rendered by templates** from structured data. The LLM writes only the history-of-present-illness narrative.
5. **Every fact has a trust label:** `patient_said`, `from_report`, `doctor_verified`, or `rejected`.
6. **Unclear OCR is never guessed.** Mark it unreadable and link to the image.
7. **Never store Aadhaar numbers.** ABHA only.
8. **Every create/update/verify writes to the hash-chained audit log.**
9. **Nothing leaves the hospital directly.** External sends go through the outbox; the outbox does not drain in island mode; consent is re-checked at send time.
10. **The kiosk keeps no patient data after a session ends** (memory and cache cleared).
11. **Every question is answerable by voice or by tap.**
12. **Allergies are always shown to the doctor**, verified or not.

## 7. Accessibility rules (kiosk and patient app)

- Body text ≥ 20sp, buttons ≥ 24sp, touch targets ≥ 56dp.
- Every screen has an audio prompt and a replay button.
- Icons plus words on every choice; never rely on reading alone.
- Hindi strings are everyday Hindi, never Sanskrit clinical terms (those appear only on the doctor's side).
- Large-text and high-contrast modes exist.

## 8. Coding conventions

- **Python:** type hints everywhere; Pydantic/SQLModel models for all request/response bodies; business logic in `services/`, HTTP in `routers/`; `ruff` formatting; no global mutable state except caches loaded at startup.
- **TypeScript:** `strict: true`; types for every contract payload live in `web/src/api/types.ts`; no `any`.
- **Kotlin:** single Activity, Compose, one ViewModel per flow; network calls in repositories; data classes mirror `CONTRACTS.md`.
- **Naming:** JSON is `snake_case`; enum values exactly as in `CONTRACTS.md §2`.
- **Errors:** `{"error": {"code": "...", "message": "..."}}` (see `CONTRACTS.md §1`).
- **Time:** UTC ISO 8601 with `Z`. **IDs:** UUID4 strings.
- **Secrets:** only via `.env`; never committed.

## 9. Definition of done (every task)

- [ ] Only the files the task names were created or changed.
- [ ] The task's **Acceptance** checks pass (commands shown in the task).
- [ ] Tests added where the task asks, and `pytest` / `tsc --noEmit` / Gradle build pass.
- [ ] No change to `CONTRACTS.md` (proposals go to `docs/contract-change-requests.md`).
- [ ] `PROGRESS.md` updated: task ticked, plus a one-line note for later tasks if anything matters.
- [ ] Committed: `git add -A && git commit -m "T-<ID>: <task title>"` (one commit per task, so any task can be reverted).

## 10. Out of scope for the MVP

Real ABDM integration (mocked), real SMS (log only), handwriting recognition (marked unreadable),
multiple hospitals, iOS, badge hardware (PIN instead), Unani/Siddha/Homoeopathy modes,
paediatric/obstetric/psychiatric pathways. Mention these as roadmap, don't build them.

**In the pitch architecture but not built in the MVP** (describe them, don't build them): standby second server,
write-once and off-site backups, GPS time source, split master-key shares, locked switch ports, badge readers,
SMS through a GSM modem (the display board and logs stand in), consent revocation from the patient app.

## 11. How to run (once tasks F1–F6 exist)

```bash
docker compose up -d postgres          # database
ollama serve & ollama pull qwen2.5:3b-instruct-q4_K_M
make server    # uvicorn server on 0.0.0.0:8000
make nlp       # nlp service on 0.0.0.0:8001
make relay     # alarm relay on :8003
make his       # mock HIS on :8002
make web       # vite dev server on :5173
python scripts/seed.py
```
Android: set the server URL (Mac's hotspot IP) in the hidden settings screen (long-press the logo 3 s).
