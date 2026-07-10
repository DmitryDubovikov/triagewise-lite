.PHONY: check up down test fmt eval eval-build eval-record cache-stats traffic drift-report judge judge-report promote loop

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

# Online LLM-as-judge (iter 5b) — LIVE, costs money (rule 4): phoenix.evals judges sampled
# traced spans at JUDGE_TIER (~$0.03-0.10 over the two fixture batches) and writes verdicts
# back as span annotations. Incremental: already-judged spans are skipped, so re-running
# without new traffic is a no-op and $0. Needs `make up` + `make traffic` + .env with key.
judge:
	@test -f .env || { echo "judge is live and needs .env with OPENAI_API_KEY (rule 4)"; exit 1; }
	uv run python -m app.cli.judge

# Judge verdicts from Phoenix's span store, not the UI (rule 8). Exit 0 = judged spans exist.
judge-report:
	uv run python -m scripts.judge_report

# Promotion loop, one manual turn (iter 6a) — replay, offline, $0: re-eval champion vs
# challenger on the golden set (derived cassettes), strict gate, swap alias `champion` on a
# challenger win, verify in the store (rule 8). Idempotent: a re-run after the swap is a no-op.
# Needs `make up` + synced prompts (uv run python -m scripts.register_prompt) + golden (dvc pull).
promote:
	uv run python -m app.cli.promote

# Prefect hygiene (iter 6b), same posture as PROMPTFOO_ENV: client state stays
# project-local (./.prefect, gitignored), the runner talks to the Compose server (schedules
# are server-side in Prefect 3), and analytics stay off even if a client ever falls back to
# an ephemeral API. EXTRA_LOGGERS=app: ticks run in a runner subprocess where prefect owns
# logging (root=WARNING) — this hands app.* loggers to prefect so the access-layer SLO
# lines (tier+cost, iter 3) stay visible in flow-run logs instead of vanishing.
PREFECT_ENV = PREFECT_HOME=$(PWD)/.prefect PREFECT_API_URL=http://localhost:4200/api \
	PREFECT_SERVER_ANALYTICS_ENABLED=false PREFECT_LOGGING_EXTRA_LOGGERS=app

# Continuous-evaluation loop (iter 6b) — replay, offline, $0: serve() registers the flow +
# interval schedule on the Compose Prefect server and polls for the ticks it creates every
# LOOP_INTERVAL_SECONDS (default 60); each tick reruns the 6a promotion turn on the host.
# Ctrl-C stops the runner; the server-side schedule keeps ticking, so unserved runs just
# queue as Scheduled/Late — harmless here because every promotion tick is idempotent (post-
# swap it's a no-op: alias doesn't drift, versions don't pile), so a backlog changes nothing
# in the store. Needs `make up` + synced prompts + golden (dvc pull), like `make promote`.
loop:
	$(PREFECT_ENV) uv run python -m app.cli.loop

# Control-plane backends (MLflow :5050, Phoenix :6006, Prefect :4200) + the read-only
# dashboard (:8501, iter 7). --build: the dashboard image rebuilds when its Dockerfile/
# requirements change and is a cheap cache no-op otherwise.
up:
	docker compose up -d --build mlflow phoenix prefect dashboard

down:
	docker compose down
