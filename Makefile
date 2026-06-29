.PHONY: check up down test fmt

# Static gate: lint + format + types. No network, no LLM.
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy app
	uv run pytest

test:
	uv run pytest

fmt:
	uv run ruff format .
	uv run ruff check --fix .

# Control-plane backend (MLflow) — localhost:5000.
up:
	docker compose up -d mlflow

down:
	docker compose down
