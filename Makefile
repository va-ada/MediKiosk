.PHONY: db-up db-down server nlp relay his web test seed demo-reset

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

server:
	cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

nlp:
	cd nlp && uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

relay:
	cd relay && uv run uvicorn main:app --host 0.0.0.0 --port 8003

his:
	cd mock_his && uv run uvicorn main:app --host 0.0.0.0 --port 8002

web:
	cd web && npm run dev -- --host 0.0.0.0 --port 5173

test:
	cd server && uv run pytest -q
	cd nlp && uv run pytest -q
	cd relay && uv run pytest -q
	cd mock_his && uv run pytest -q
	cd web && npx tsc --noEmit -p tsconfig.app.json
	python3 scripts/validate_content.py

seed:
	cd server && uv run python ../scripts/seed.py

# DESTRUCTIVE: wipes the local demo database and patient files, then loads the three demo patients.
demo-reset:
	cd server && uv run python ../scripts/reset_demo.py --yes
