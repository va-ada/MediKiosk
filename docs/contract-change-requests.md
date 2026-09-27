# Contract change requests

Proposals to change `CONTRACTS.md`. Each entry: date, task ID, what changes, why. The team decides; Claude never edits `CONTRACTS.md` directly.

## 2026-09-27 · S3 · New error code `consent_required` (informational — already implemented)
- **What:** `POST /api/sessions/{id}/triage` returns `409 {"error":{"code":"consent_required"}}` when the session has no consent yet (status `identifying`).
- **Why:** §4.3 doesn't define an error for triage-before-consent; issuing a token without consent would break rule 9 (consent re-checked at send time needs a consent row). Kiosk and desk always consent first, so normal flows never see it.
- **Also:** triage is idempotent per session — a retry returns the existing token instead of issuing a second one.
- **Decision needed:** accept the code into §4.3, or pick another.

## 2026-09-27 · S5 · New error code `invalid_state` (informational — already implemented)
- **What:** token actions on a token in the wrong status return `409 invalid_state` (e.g. outcome on a `waiting` token, reactivate on a non-`absent` token, call on a `done` token).
- **Why:** §4.6 only names `already_in`. Without a guard, double-clicks could, for example, close a finished visit twice or push a `done` token back to `waiting`.
- **Also:** `in` pressed twice by the same doctor returns 200 (idempotent); `call`/`queue/next` record the calling doctor in `token.doctor_id` so the display board can show doctor + room.

## 2026-09-27 · N1 · New NLP error code `invalid_audio` (informational — already implemented)
- **What:** `POST /asr` returns `422 {"error":{"code":"invalid_audio"}}` when ffmpeg cannot decode the upload (empty/corrupt file).
- **Why:** §6 only defines `503 model_loading`; a corrupt upload is a client error, not "model loading". The server (S7) maps any NLP error to `503 nlp_unavailable` for the kiosk anyway, so kiosks never see this code.
