---
description: Run every automated check in the MediKiosk repo and report
---
Run whichever of these exist (skip the rest): `cd server && uv run pytest -q`; `cd nlp && uv run pytest -q`; `cd relay && uv run pytest -q`; `cd mock_his && uv run pytest -q`; `cd web && npx tsc --noEmit`; `python3 scripts/validate_content.py`; `cd android && ./gradlew assembleDebug`.
Report a table: component / result / failing tests. Do not fix anything — only report, then suggest which task card each failure most likely belongs to.
