# MediKiosk — Contracts (single source of truth)

Every task follows this file **exactly**. Names, paths, fields and enum values here are final.
Changing anything requires team agreement: write the proposal in `docs/contract-change-requests.md`.

---

## §1 Conventions

| Item | Rule |
|---|---|
| Base URLs | server `http://<MAC_IP>:8000` · nlp `:8001` · mock HIS `:8002` · relay `:8003` · web `:5173` |
| Format | JSON, `snake_case` keys, UTF-8 (Hindi in Devanagari) |
| IDs | UUID4 strings; exceptions: `audit_log.id` (int), `token.number` (int) |
| Time | ISO 8601 UTC with `Z` (e.g. `2026-10-12T05:31:00Z`); `token.day` is the local date (Asia/Kolkata) |
| Languages | `hi`, `en` |
| Errors | HTTP 4xx/5xx with `{"error": {"code": "snake_case_code", "message": "human readable"}}` |
| Kiosk/app auth (K) | Header `X-Kiosk-Id: KIOSK-01` / `HALL-01` / `APP-FOLD` / `DESK-01` (assisted desk web page) (missing → 400 `missing_kiosk_id`) |
| Staff auth (S:role) | `Authorization: Bearer <jwt>` from `POST /api/staff/login`; wrong role → 403 `forbidden` |
| Public (P) | No auth |
| Lists | Accept `?limit=` (default 100); no pagination in MVP |

## §2 Enums (use these exact strings)

```
sex:               M | F | O
language:          hi | en
role:              doctor | nurse | desk | admin
department:        general | ayurveda
informant:         self | proxy
legal_basis:       consent | medical_emergency
session_status:    identifying | consented | triaged | history | documents | verifying | submitted | with_doctor | closed
lane:              emergency | priority | normal
token_status:      waiting | called | in | no_show | absent | done | referred
outcome:           out | recheck | refer | followup
answer_source:     voice | tap | staff
answer_status:     confident | uncertain
section:           complaint | hpi | pmh | drugs | allergies | family | personal | ros | labs | ayush
trust:             patient_said | from_report | doctor_verified | rejected
source_type:       answer | document | doctor | carried
doc_type:          lab_report | prescription | discharge_summary | unknown
doc_status:        pending | processed | failed
alert_level:       urgent | emergency
alert_source:      button | rule
alert_status:      open | acknowledged | confirmed | downgraded
reason_code:       chest_pain | breathing | bleeding | unconscious | seizure | stroke_signs | severe_pain | pregnancy | other
complaint_code:    joint_pain | fever | cough | stomach | headache | chest_pain | breathing | skin | other
readback_response: yes | no | not_sure
outbox_status:     pending | sent | skipped_no_consent | failed
device_mode:       KIOSK | HALL | PATIENT_APP
question_type:     choice | multi | yesno | number | duration | scale | free
slot_type:         string | enum | bool | number | duration_days | scale_0_10 | list_enum | list_string
```

Section display order (doctor view): `complaint, hpi, allergies, drugs, pmh, labs, family, personal, ros, ayush`.

## §3 Data model (SQLModel tables in `server/app/models.py`)

| Table | Fields |
|---|---|
| **staff** | id, name, role, department (nullable), room (nullable), pin_hash, active (bool) |
| **patient** | id, hospital_id (unique, `MK-000001`), name, age (int), sex, language, abha_number (nullable, unique, 14 digits), created_at |
| **session** | id, patient_id, kiosk_id, informant, informant_relation (nullable), status, legal_basis, complaint_code (nullable), pathway (nullable), department (nullable), created_at, submitted_at, opened_by_doctor_at, closed_at (all nullable except created_at) |
| **consent** | id, session_id, capture, scan, share_hospital, link_abha, check_passed (bools), created_at, revoked_at (nullable) |
| **token** | id, display (`A-017`), prefix, number (int), day (date), patient_id, session_id, department, lane, status, arrival_seq (int), called_count (int), doctor_id, preferred_doctor_id, created_at, called_at, in_at, closed_at, outcome, outcome_note, followup_date (nullable where sensible) |
| **answer** | id, session_id, question_id, source, raw_text (nullable), confidence (float, nullable), slots (JSON), status, created_at |
| **fact** | id, session_id, patient_id, section, key, value (JSON), text_en, patient_words (nullable), trust, source_type, source_id (nullable), bbox (JSON, nullable), created_at, verified_by, verified_at (nullable) |
| **document** | id, session_id, patient_id, file_path, page_no (int), doc_type, doc_date (date, nullable), ocr_json (JSON, nullable), status, pinned (bool), created_at |
| **readback** | id, session_id, fact_id, response (nullable), created_at |
| **alert** | id (client may supply), kiosk_id, session_id (nullable), level, reason_code (nullable), rule_id (nullable), reason_text, source, status, escalated (bool), created_at, acknowledged_by, acknowledged_at, resolved_by, resolved_at (nullable) |
| **summary** | id, session_id, version (int), payload (JSON), generated_at |
| **section_view** | id, session_id, staff_id, section, opened_at |
| **section_approval** | id, session_id, section, staff_id, approved_at |
| **diagnosis** | id, session_id, staff_id, codes (JSON list of `{system, code, display}`), text (nullable), created_at |
| **audit_log** | id (int, autoincrement), ts, actor, action, entity, entity_id, details (JSON), prev_hash, hash |
| **outbox** | id, kind (`fhir_bundle`), session_id, patient_id, payload (JSON), idempotency_key (unique), status, attempts (int), last_error (nullable), next_attempt_at, created_at, sent_at (nullable) |
| **patient_key** | patient_id (PK), wrapped_key (base64 str, nullable after erase), created_at, destroyed_at (nullable) |
| **setting** | key (PK), value (JSON). Known keys: `island_mode` (bool) |

Fact `value` shapes by section: `labs` → `{test, value, unit, ref_low, ref_high, flag, date}`; `drugs` → `{name, name_as_written, dose, frequency, duration, matched, found_in_documents}`;
any fact may carry `{"readable": false}`, `{"patient_disputed": true}` or `{"patient_unsure": true}`.

## §4 Server API (`server`, port 8000)

### 4.1 Health and staff
| Method & path | Auth | Request | Response |
|---|---|---|---|
| GET `/api/health` | P | — | `{"status":"ok","version":"0.1.0"}` |
| POST `/api/staff/login` | P | `{staff_id, pin}` | `{token, staff:{id,name,role,department,room}}` · 401 `invalid_pin` |

### 4.2 Patients
| Method & path | Auth | Request | Response |
|---|---|---|---|
| POST `/api/patients/register` | K | `{name, age, sex, language}` | Patient |
| POST `/api/patients/abha/verify` | K | `{abha_number, otp}` | Patient · 401 `invalid_otp` (valid OTP is `123456`) · 404 `abha_not_found` |
| GET `/api/patients/{id}` | K or S | — | Patient |

ABHA lookup: existing patient with that `abha_number`, else create from `content/mock_abha.json`, else 404.

### 4.3 Sessions and intake
| Method & path | Auth | Request | Response |
|---|---|---|---|
| POST `/api/sessions` | K | `{patient_id, informant, informant_relation?}` | Session (status `identifying`) |
| GET `/api/sessions/{id}` | K or S | — | Session |
| POST `/api/sessions/{id}/consent` | K | `{capture, scan, share_hospital, link_abha, check_passed}` | Consent (session → `consented`) |
| POST `/api/sessions/{id}/triage` | K | `{complaint_code, complaint_text?, body_part?, redflags:{chest_pain, breathless, stroke_signs, heavy_bleeding, fainted}}` | `{session, token: QueueItem, alerts:[Alert]}` (session → `triaged`) |
| GET `/api/sessions/{id}/next-question?language=hi` | K | — | `{"done": false, "question": Question (§11.4)}` or `{"done": true}` |
| POST `/api/sessions/{id}/answers` | K | `{question_id, source:"tap", value}` (value typed per slot_type) | `{answer, next, alerts}` where `next` = next-question response |
| POST `/api/sessions/{id}/answers/audio` | K | multipart: `question_id`, `language`, `audio` (file) | `{answer, next, alerts, fallback_choices}` — if uncertain: `next` is the **same** question and `fallback_choices` = its choices; 503 `nlp_unavailable` if NLP down |

### 4.4 Documents
| Method & path | Auth | Request | Response |
|---|---|---|---|
| POST `/api/sessions/{id}/documents` | K | multipart: `image` (jpeg/png ≤ 10 MB), `page_no` | Document (status `pending`; processed asynchronously) |
| GET `/api/documents/{id}` | K or S | — | Document |
| GET `/api/documents/{id}/image` | S | — | image bytes (decrypted) · 410 `patient_erased` |

### 4.5 Read-back and submit
| Method & path | Auth | Request | Response |
|---|---|---|---|
| GET `/api/sessions/{id}/readback?language=hi` | K | — | `{items:[{fact_id, text, text_en}]}` |
| POST `/api/sessions/{id}/readback` | K | `{fact_id, response}` | `{ok: true}` |
| POST `/api/sessions/{id}/submit` | K | — | `{session, summary_version}` (session → `submitted`) |

### 4.6 Queue and tokens
| Method & path | Auth | Request | Response |
|---|---|---|---|
| GET `/api/queue?department=ayurveda` | S:doctor,nurse | — | `[QueueItem]` in preview order (§10.2) |
| POST `/api/queue/next` | S:doctor | `{department}` | QueueItem (now `called`) · 204 if empty |
| POST `/api/tokens/{id}/call` | S:doctor | — | QueueItem |
| POST `/api/tokens/{id}/in` | S:doctor | — | QueueItem · 409 `already_in` |
| POST `/api/tokens/{id}/no-show` | S:doctor | — | QueueItem |
| POST `/api/tokens/{id}/reactivate` | K or S | — | QueueItem |
| POST `/api/tokens/{id}/outcome` | S:doctor | `{outcome, refer_department?, followup_date?, results_tomorrow?, admit?, note?}` | QueueItem |
| POST `/api/doctors/signout` | S:doctor | — | `{returned_tokens: n}` |
| GET `/api/display/state?department=` | P | — | DisplayState (§11.5) |

### 4.7 Doctor review
| Method & path | Auth | Request | Response |
|---|---|---|---|
| GET `/api/sessions/{id}/summary` | S:doctor | — | Summary (§11.1); first call sets `opened_by_doctor_at`, session → `with_doctor` |
| POST `/api/sessions/{id}/sections/{section}/open` | S:doctor | — | `{ok: true}` |
| POST `/api/sessions/{id}/sections/{section}/approve` | S:doctor | — | `{ok: true}` · 409 `section_not_opened` |
| POST `/api/facts/{id}/verify` | S:doctor | `{action: approve\|edit\|reject, value?, text_en?}` | Fact |
| POST `/api/sessions/{id}/ayush-exam` | S:doctor | `{nadi?, jihva?, pramana?:{height_cm, weight_kg}, sara?, samhanana?, vikriti?, notes?}` | `{facts:[Fact]}` (trust `doctor_verified`, section `ayush`) |
| POST `/api/sessions/{id}/diagnosis` | S:doctor | `{codes:[{system, code, display}], text?}` | `{ok: true}` |

### 4.8 Alerts
| Method & path | Auth | Request | Response |
|---|---|---|---|
| POST `/api/alerts/emergency` | K | `{id, kiosk_id, reason_code, session_id?}` | Alert (idempotent on `id`) |
| GET `/api/alerts?status=open,acknowledged` | S:nurse,doctor | — | `[Alert]` |
| POST `/api/alerts/{id}/ack` | S:nurse,doctor | — | Alert |
| POST `/api/alerts/{id}/resolve` | S:nurse,doctor | `{outcome: confirmed\|downgraded}` | Alert — confirmed → session's token lane `emergency`; downgraded → lane `normal`, same `arrival_seq` |

### 4.9 Admin
| Method & path | Auth | Request | Response |
|---|---|---|---|
| GET `/api/admin/health` | S:admin | — | `{db, nlp, relay, his, ollama, island_mode}` (bools) |
| GET / POST `/api/admin/island` | S:admin | POST `{enabled}` | `{enabled}` |
| GET `/api/admin/outbox` | S:admin | — | `[Outbox]` |
| GET `/api/admin/audit?limit=` | S:admin | — | `[AuditLog]` newest first |
| GET `/api/admin/audit/verify` | S:admin | — | `{valid, checked, first_bad_id}` |
| POST `/api/admin/patients/{id}/erase` | S:admin | `{approver_staff_id, approver_pin}` (a **different** admin) | `{destroyed: true}` |

### 4.10 Terminology
| GET `/api/terminology/search?q=&system=` | S:doctor | — | `[{system, code, display, sample}]` (max 10) |
|---|---|---|---|

## §5 WebSocket events

Server: `ws://<host>:8000/ws?channel=queue|alerts|display|admin`. Message: `{"type": "...", "data": {...}, "ts": "..."}`.

| type | channels | data |
|---|---|---|
| `token.created`, `token.updated` | queue, display | QueueItem |
| `token.called` | queue, display | QueueItem + `{doctor_name, room}` |
| `alert.created`, `alert.updated` | alerts, admin | Alert |
| `summary.ready` | queue | `{session_id, version}` |
| `document.processed` | queue | Document |
| `island.changed` | admin | `{enabled}` |

## §6 NLP service API (`nlp`, port 8001)

| Method & path | Request | Response |
|---|---|---|
| GET `/health` | — | `{asr_loaded, ocr_loaded, ollama}` (bools) |
| POST `/asr` | multipart: `audio` (webm/ogg/m4a/mp4/wav), `language` | `{text, confidence (0–1), duration_sec}` · 503 `model_loading` |
| POST `/extract` | `{question_id, language, text, question_text_en, slots:[{name, type, enum?}]}` | `{slots:{name: value\|null}, status: confident\|uncertain, notes:[str]}` |
| POST `/document` | multipart: `image` | `{doc_type, doc_date, lines:[{text, bbox:[x,y,w,h], conf}], entities:[Entity]}` |
| POST `/summarize` | `{language:"en", facts:[{section, key, value, text_en}]}` | `{narrative, unsupported_terms:[str], fallback_used}` |

Entity: `{kind: lab|drug|diagnosis, value: {...}, text_en, bbox, conf, readable}` with lab/drug value shapes as in §3.

## §7 Alarm relay (`relay`, port 8003) — independent of the API server

| Method & path | Request | Response |
|---|---|---|
| POST `/alarm` | `{id, kiosk_id, reason_code, created_at}` | `{ok: true, duplicate: bool}` |
| GET `/alarms` | — | last 50 alarms |
| WS `/ws` | — | messages `{"type":"alarm","data":{...}}` |
| GET `/health` | — | `{status:"ok"}` |

## §8 Mock HIS (`mock_his`, port 8002)

| Method & path | Request | Response |
|---|---|---|
| POST `/fhir` | FHIR R4 Bundle JSON; header `Idempotency-Key` (required) | `{received: true, id, duplicate: bool}` |
| GET `/bundles` | — | JSON list of received bundles |
| GET `/` | — | HTML page listing bundles |

## §9 Content files (`content/`)

### 9.1 Question graph — `content/questions/<pathway>.yaml`
```yaml
id: joint_pain                 # pathway id (file name without .yaml)
title_en: Joint pain
start: jp_site
questions:
  - id: jp_site                # unique across ALL files; also the audio file key
    type: choice               # question_type (§2)
    section: complaint         # section (§2)
    text_en: "Which joint hurts the most?"
    text_hi: "सबसे ज़्यादा दर्द किस जोड़ में है?"
    slot: {name: site, type: enum}
    choices:                   # required for choice/multi; optional for others (used as voice fallback)
      - {value: knee, en: Knee, hi: "घुटना", icon: knee}
      - {value: back, en: Lower back, hi: "कमर", icon: back}
    next: jp_duration          # string, "end", or a rule list:
  - id: jp_swelling
    type: yesno
    section: hpi
    text_en: "Is the joint swollen?"
    text_hi: "क्या जोड़ में सूजन है?"
    slot: {name: swelling, type: bool}
    next:
      - if: {slot: swelling, is: true}
        goto: jp_swelling_where
      - goto: jp_worse         # default rule has no "if"
```
Conditions: `is`, `in`, `gte`, `lte` on any slot answered earlier in the session (including triage slots).
After a pathway ends, sessions in department `ayurveda` continue with `questions/ayush.yaml` (§9.5).

### 9.2 Triage — `content/triage.yaml`
```yaml
complaints:        # complaint_code → icon, labels, department, pathway
  - {code: joint_pain, icon: joint, en: "Joint pain", hi: "जोड़ों का दर्द", department: ayurveda, pathway: joint_pain}
  - {code: fever, icon: fever, en: "Fever", hi: "बुखार", department: general, pathway: null}
redflag_questions: # always asked, in this order; slots are bool
  - {slot: chest_pain,     en: "Do you have chest pain now?",               hi: "क्या अभी सीने में दर्द है?"}
  - {slot: breathless,     en: "Are you finding it hard to breathe?",        hi: "क्या साँस लेने में तकलीफ़ है?"}
  - {slot: stroke_signs,   en: "Sudden weakness, face drooping or slurred speech?", hi: "क्या अचानक कमज़ोरी, चेहरा टेढ़ा या बोलने में दिक्कत है?"}
  - {slot: heavy_bleeding, en: "Are you bleeding heavily?",                  hi: "क्या बहुत ज़्यादा खून बह रहा है?"}
  - {slot: fainted,        en: "Did you faint today?",                       hi: "क्या आज आप बेहोश हुए?"}
```
Pathway `null` → the session goes straight to documents after triage (MVP builds only `joint_pain`).

### 9.3 Red-flag rules — `content/redflags.yaml`
```yaml
rules:
  - id: chest_pain_breathless
    level: emergency
    reason_text: "Chest pain with breathlessness"
    all: [{slot: chest_pain, is: true}, {slot: breathless, is: true}]
  - id: fainted_today
    level: urgent
    reason_text: "Fainted today"
    any: [{slot: fainted, is: true}]
```
A rule fires when **all** `all` conditions hold **and** (if `any` exists) at least one `any` condition holds.

### 9.4 Lexicon — `content/lexicon_hi.yaml`, festivals — `content/festivals.yaml`
```yaml
terms:            # folk term → concept
  - {match: ["sugar", "शुगर"], concept: "diabetes", ambiguous: false}
  - {match: ["bp", "बीपी"], concept: "blood pressure problem", ambiguous: true}
negation_cues: ["नहीं", "नही", "ना", "मत", "nahi", "nahin", "no", "not", "never"]
numbers: {एक: 1, दो: 2, तीन: 3, ek: 1, do: 2, teen: 3}          # extend to 20
units: {day: ["दिन","din","day","days"], week: ["हफ्ता","हफ्ते","hafta","hafte","week","weeks"],
        month: ["महीना","महीने","mahina","mahine","month","months"], year: ["साल","saal","year","years"]}
```
`festivals.yaml`: `{diwali: {2025: "YYYY-MM-DD", 2026: "..."}, holi: {...}}` — dates must be copied from an official calendar, never guessed.

### 9.5 AYUSH set — `content/questions/ayush.yaml`
Same format as §9.1 with `id: ayush`, every question `section: ayush`. Patient-reportable items only; optional `doctor_note` field holds the Sanskrit term (shown only to doctors).

### 9.6 Read-back templates — `content/readback_templates.yaml`
```yaml
duration_days: {en: "Problem for {value} days", hi: "{value} दिन से तकलीफ़"}
site:          {en: "Pain in the {label_en}", hi: "{label_hi} में दर्द"}
```

### 9.7 Data files
- `drugs.csv`: `generic,brand_examples,strengths,form,system` (`system` = `allopathic` or `ayurveda`)
- `terminology.csv`: `system,code,display,sample` (`system` = `NAMASTE` | `ICD11_TM2` | `ICD10`; `sample=true` for placeholder codes)
- `mock_abha.json`: `[{"abha_number":"12345678901234","name":"Kamla Devi","age":62,"sex":"F","language":"hi"}, ...]`
- Audio: `content/audio/{hi,en}/{key}.wav` — key = question id, triage slot, or system phrase (`sys_welcome`, `sys_consent`, `sys_help_coming`, `sys_still_there`, `sys_thanks`, `sys_readback_intro`, `sys_did_you_mean`)
- Samples: `content/samples/*.png` — fake documents, each stamped "SAMPLE — NOT A REAL REPORT"

## §10 Server rules

**10.1 Token numbering.** `display = f"{SERVER_PREFIX}-{number:03d}"`. `number` = 1 + max for (prefix, day). `arrival_seq` = 1 + global max, never reused. Queue endpoints only show tokens where `day` = today.

**10.2 Queue selector** (department D):
1. Candidates: tokens in D, `day` = today, status `waiting`.
2. Any `emergency` → oldest by `arrival_seq`.
3. Else any `normal` waiting ≥ `WAIT_LIMIT_MIN` → oldest such.
4. Else any `priority` (skip those whose `preferred_doctor_id` is another doctor) → oldest.
5. Else oldest `normal`.
Preview order for `GET /api/queue`: emergency, priority, normal, each by `arrival_seq`; aged normals carry flag `aged`.

**10.3 Token actions.** call → `called`, `called_count`+1. in → `in`, `doctor_id` = caller (409 if another doctor). no-show → `absent` if `called_count` ≥ 2, else back to `waiting`. reactivate → `absent` → `waiting`. Outcomes: `out` → `done`, session `closed`, outbox entry created; `recheck` → lane `priority`, `waiting`, `preferred_doctor_id` = caller — **if** `results_tomorrow`, close today's token and create a new `waiting` priority token with `day` = tomorrow; `refer` → token `referred`, new token in `refer_department`, lane `priority`, same `arrival_seq`; `followup` → `done`, store `followup_date`. signout → clear `preferred_doctor_id` = caller on waiting tokens.

**10.4 Trust.** `patient_said`/`from_report` → `doctor_verified` (approve or edit) or `rejected` (reject). On a patient's next session, their `doctor_verified` facts in `allergies, drugs, pmh, family` are copied in with `source_type: carried`, trust `doctor_verified`.

**10.5 Summary.** Sections in §2 display order; `rejected` facts excluded. **Allergies always appear in the critical strip**, whatever their trust. Drugs `from_report` and unverified are grouped under `found_in_documents: true`, never merged with current medicines. HPI narrative from NLP `/summarize`; if unavailable, join fact `text_en` with "; ". Every rebuild stores a new `summary.version`; `new_since_opened` = facts created after `opened_by_doctor_at`.

**10.6 Outbox and island mode.** Worker every 5 s. If `island_mode` → send nothing. Before each send, re-check consent (`share_hospital` true and not revoked) → else `skipped_no_consent`. POST to HIS with `Idempotency-Key` = `{session_id}:v{summary_version}`. 2xx → `sent`; otherwise `attempts`+1 and `next_attempt_at` = now + min(5 s × 2^attempts, 300 s).

**10.7 Audit chain.** `hash = sha256_hex(prev_hash + canonical_json({ts, actor, action, entity, entity_id, details}))`, where canonical_json = `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. First `prev_hash` = 64 zeros. `actor` = `kiosk:<id>` | `staff:<id>` | `system`.

**10.8 Encryption and erasure.** AES-256-GCM. Per-patient 32-byte data key, wrapped by `MASTER_KEY_B64` and stored base64 as `nonce(12) + ciphertext`. Files on disk = `nonce(12) + ciphertext`. Erase sets `destroyed_at` and clears `wrapped_key`; afterwards decrypt → 410 `patient_erased`.

**10.9 Kiosk wipe.** After submit, emergency hand-off, or 60 s inactivity + 30 s countdown, the app clears all in-memory patient state and cache files and returns to Start. Resume uses the token QR payload `{"session_id": "...", "token_id": "..."}`.

## §11 Example payloads

**11.1 Summary** (`GET /api/sessions/{id}/summary`)
```json
{
  "session_id": "5f0c…", "version": 3, "generated_at": "2026-10-12T05:31:00Z",
  "patient": {"id": "a1b2…", "hospital_id": "MK-000123", "name": "Kamla Devi", "age": 62, "sex": "F",
              "language": "hi", "abha_number": null},
  "informant": {"type": "self", "relation": null},
  "token": {"display": "A-017", "department": "ayurveda"},
  "critical": {
    "allergies": [{"fact_id": "f1", "text": "Penicillin — rash", "trust": "patient_said"}],
    "red_flags": [],
    "abnormal_labs": [{"fact_id": "f9", "text": "Haemoglobin 10.2 g/dL (ref 12.0–15.0) LOW", "trust": "from_report"}]
  },
  "sections": [
    {"key": "complaint", "title": "Chief complaint", "opened": false, "approved": false,
     "items": [{"fact_id": "f2", "text": "Knee pain", "trust": "patient_said", "patient_words": "ghutne mein dard", "flags": []}]},
    {"key": "hpi", "title": "History of present illness", "opened": false, "approved": false,
     "narrative": "Knee pain for 3 months, worse on climbing stairs; no fever.",
     "items": [{"fact_id": "f3", "text": "Duration: 90 days", "trust": "patient_said", "patient_words": "teen mahine se", "flags": []}]},
    {"key": "drugs", "title": "Medicines", "opened": false, "approved": false,
     "items": [{"fact_id": "f7", "text": "Metformin 500 mg twice daily", "trust": "from_report", "found_in_documents": true,
                "source": {"document_id": "d1", "bbox": [120, 340, 400, 28]}, "flags": []}]}
  ],
  "documents": [{"id": "d1", "doc_type": "prescription", "doc_date": "2026-08-12", "pinned": false,
                 "image_url": "/api/documents/d1/image", "status": "processed"}],
  "new_since_opened": []
}
```
`flags` may contain `unreadable`, `patient_disputed`, `patient_unsure`, `carried`.

**11.2 QueueItem**
```json
{"id": "t1", "display": "A-017", "lane": "normal", "status": "waiting", "department": "ayurveda",
 "session_id": "5f0c…", "patient": {"name": "Kamla Devi", "age": 62, "sex": "F", "language": "hi"},
 "complaint": "Joint pain", "arrival_seq": 42, "created_at": "2026-10-12T04:58:00Z", "wait_min": 33,
 "flags": ["red_flag", "aged", "recheck", "referred"], "called_count": 0,
 "doctor_id": null, "doctor_name": null, "preferred_doctor_id": null}
```

**11.3 Alert**
```json
{"id": "b7e1…", "kiosk_id": "KIOSK-01", "session_id": null, "level": "emergency", "reason_code": "chest_pain",
 "rule_id": null, "reason_text": "Emergency button: chest pain", "source": "button", "status": "open",
 "escalated": false, "created_at": "2026-10-12T05:02:11Z", "acknowledged_by": null, "resolved_by": null}
```

**11.4 Question** (sent to kiosk; `text` is in the requested language)
```json
{"id": "jp_duration", "type": "duration", "section": "hpi",
 "text": "कितने समय से दर्द है?", "text_en": "How long have you had this pain?", "audio": "jp_duration",
 "choices": [], "slot": {"name": "duration_days", "type": "duration_days"},
 "allow_voice": true, "progress": {"answered": 3, "remaining_estimate": 9}}
```

**11.5 DisplayState**
```json
{"department": "ayurveda",
 "now_serving": [{"display": "A-016", "doctor_name": "Dr. Mehta", "room": "Room 1", "called_at": "2026-10-12T05:20:00Z"}],
 "next": ["A-017", "A-018", "A-019"]}
```
