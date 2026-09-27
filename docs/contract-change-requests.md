# Contract change requests

Proposals to change `CONTRACTS.md`. Each entry: date, task ID, what changes, why. The team decides; Claude never edits `CONTRACTS.md` directly.

## 2026-09-27 · S3 · New error code `consent_required` (informational — already implemented)
- **What:** `POST /api/sessions/{id}/triage` returns `409 {"error":{"code":"consent_required"}}` when the session has no consent yet (status `identifying`).
- **Why:** §4.3 doesn't define an error for triage-before-consent; issuing a token without consent would break rule 9 (consent re-checked at send time needs a consent row). Kiosk and desk always consent first, so normal flows never see it.
- **Also:** triage is idempotent per session — a retry returns the existing token instead of issuing a second one.
- **Decision needed:** accept the code into §4.3, or pick another.
