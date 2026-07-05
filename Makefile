.PHONY: check up down test fmt eval eval-build eval-record cache-stats traffic drift-report

# promptfoo hygiene: telemetry/update pings off. Note: promptfoo's own cache hashes the
# whole request INCLUDING the API key, so a committed cache can't replay keyless in CI —
# the replay artifact is eval/outputs.json + eval/replay_provider.py instead. The local
# record cache (gitignored) only makes unchanged re-records free.
PROMPTFOO_ENV = PROMPTFOO_DISABLE_TELEMETRY=1 PROMPTFOO_DISABLE_UPDATE=1

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

# Regenerate eval/ assets from the DVC-versioned golden set (deterministic, offline).
eval-build:
	uv run python -m scripts.build_eval

# The CI eval gate: promptfoo replays committed eval/outputs.json via the file-replay
# provider — offline, $0, no key. promptfoo exits 0 when it aborts on provider errors,
# so the jq post-check is the actual gate: red unless every test ran and passed
# (a replay miss after a prompt change = provider error = red).
eval:
	$(PROMPTFOO_ENV) PROMPTFOO_CACHE_ENABLED=false PROMPTFOO_PYTHON=python3 \
		npx promptfoo eval -c eval/promptfooconfig.yaml \
		--providers file://replay_provider.py \
		--no-progress-bar --output eval/.results.json
	jq -e --argjson n "$$(jq '.outputs | length' eval/outputs.json)" \
		'.results.stats | .failures == 0 and .errors == 0 and .successes == $$n' \
		eval/.results.json >/dev/null \
		|| { echo "eval gate RED: failures/errors present or not every test ran"; exit 1; }
	@echo "eval gate green: $$(jq '.results.stats.successes' eval/.results.json) tests passed"

# Records the replay artifact LIVE — costs money (rule 4), run only on an explicit go:
# promptfoo's own OpenAI provider runs the golden set, then the extractor distills the
# outputs into eval/outputs.json (commit it).
eval-record:
	@test -f .env || { echo "eval-record needs .env with OPENAI_API_KEY"; exit 1; }
	set -a && . ./.env && set +a && $(PROMPTFOO_ENV) \
		PROMPTFOO_CACHE_ENABLED=true PROMPTFOO_CACHE_PATH=eval/.promptfoo-cache \
		npx promptfoo eval -c eval/promptfooconfig.yaml --no-progress-bar \
		--output eval/.record-results.json
	uv run python -m scripts.extract_eval_outputs

# Semantic-cache hit-rate over the SLO log (iter 4; jq per rule 9). Counts only calls that
# took the cached path (hit|miss) — cache=off calls don't dilute the rate.
cache-stats:
	@test -f logs/llm_calls.jsonl || { echo "no SLO log yet (logs/llm_calls.jsonl)"; exit 1; }
	@jq -s '[.[] | select(.cache == "hit" or .cache == "miss")] \
		| length as $$n | ([.[] | select(.cache == "hit")] | length) as $$h \
		| if $$n == 0 then "no cached-path calls in the log yet" \
		else {cached_path_calls: $$n, hits: $$h, hit_rate: ($$h / $$n)} end' \
		logs/llm_calls.jsonl

# Both traffic batches through triage, traced to Phoenix (iter 5a) — replay, offline, $0.
# Traces are append-only; re-running adds spans but never flips the drift verdict (the
# report compares per-batch distributions).
traffic:
	PHOENIX_ENABLED=1 uv run python -m app.cli.batch fixtures/tickets.jsonl --batch base
	PHOENIX_ENABLED=1 uv run python -m app.cli.batch fixtures/tickets_postrelease.jsonl --batch postrelease

# Drift verdict from Phoenix's span store, not the UI (rule 8). Exit 0 = drift caught.
drift-report:
	uv run python -m scripts.drift_report

# Control-plane backends (MLflow :5050, Phoenix :6006).
up:
	docker compose up -d mlflow phoenix

down:
	docker compose down
