.PHONY: db-up db-down server nlp relay his web test

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

server:
	@echo "server: not created yet (task F2)"

nlp:
	@echo "nlp: not created yet (task N1)"

relay:
	@echo "relay: not created yet (task S10)"

his:
	@echo "his: not created yet (task D1)"

web:
	@echo "web: not created yet (task W1)"

test:
	@echo "test: no test suites yet"
