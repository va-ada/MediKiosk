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

## 2026-09-27 · N5 · New NLP error code `invalid_image` (informational — already implemented)
- **What:** `POST /document` returns `422 {"error":{"code":"invalid_image"}}` when the upload cannot be decoded as an image; `503 model_loading` if the OCR engine failed to load.
- **Why:** §6 defines no errors for `/document`. S11 already validates type/size before calling NLP and marks the document `failed` on any NLP error, so kiosks never see this code.

## 2026-09-27 · S19 · Security gaps the contract leaves open (proposals — NOT implemented)
Everything §4 marks is enforced (a test walks every route). These three are outside §4 and need a team decision:

1. **WebSocket channels are unauthenticated (§5).** `queue`, `alerts` and `admin` broadcast patient names, complaints and alert details to anyone on the LAN who opens `ws://…/ws?channel=queue`.
   *Proposal:* require `?token=<staff jwt>` for `queue|alerts|admin` (close 1008 if missing/invalid or wrong role); `display` stays public (tokens + doctor/room only). Web `useChannel` would pass the token.
2. **Staff PINs are 4 digits with no attempt limit (§4.1).** 10,000 combinations can be tried in minutes.
   *Proposal:* after 5 wrong PINs for a staff id, `429 too_many_attempts` for 5 minutes (audited). Kept server-side in the DB so restarts don't reset it.
3. **The kiosk header is only an identifier (§1 "K").** Any LAN device can send `X-Kiosk-Id: KIOSK-01` and register patients, answer questions or raise alarms.
   *Proposal:* per-device secret `X-Kiosk-Key` provisioned in the hidden settings screen and checked against a `kiosk_device` list in `.env`/settings. (Demo-acceptable as is on an isolated hotspot; required before any real deployment.)
