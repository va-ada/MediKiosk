.PHONY: db-up db-down server nlp relay his web test

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

server:
	cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

nlp:
	@echo "nlp: not created yet (task N1)"

relay:
	cd relay && uv run uvicorn main:app --host 0.0.0.0 --port 8003

his:
	@echo "his: not created yet (task D1)"

web:
	@echo "web: not created yet (task W1)"

test:
	cd server && uv run pytest -q
