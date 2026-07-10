# triagewise-lite

An **LLMOps control plane** built over a deliberately trivial fixture: triaging synthetic
support tickets for a fictional SaaS (*Driftwood*). The app is a fixture; **the ops is the
product** — prompt registry, CI eval-gates, online evaluation, drift monitoring, and a
continuous-evaluation loop. See `CLAUDE.md` (constitution) and `ROADMAP.md` (iteration backbone).

## Quickstart (through iter 6a — champion/challenger promotion loop)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use
make up                         # backends: MLflow :5050, Phoenix :6006, Prefect :4200
                                # + read-only control-plane dashboard at http://localhost:8501 (iter 7)

# Register the triage prompt as a versioned artifact with champion/challenger aliases.
# Talks to the registry only — no LLM call, costs nothing.
uv run python -m scripts.register_prompt

# Triage one ticket — loads the champion prompt by alias; LLM is offline/$0 in replay (default).
uv run python -m app.cli.main DW-001

# Semantic cache (iter 4, opt-in): a close-enough repeat is served from the cache — no cassette,
# no network. DW-011 is a paraphrase of DW-001 and has no cassette of its own; the first command
# seeds the cache (miss), the second is a semantic hit. First run downloads the embedding model
# once (~30 MB, not LLM money). `make cache-stats` prints the hit-rate from the SLO log.
SEMANTIC_CACHE_ENABLED=1 uv run python -m app.cli.main DW-001
SEMANTIC_CACHE_ENABLED=1 uv run python -m app.cli.main DW-011
make cache-stats

# Drift monitoring (iter 5a): triage both traffic batches with Phoenix tracing (replay, $0),
# then ask Phoenix's span store for the verdict — the post-release batch introduces the
# `automation` category and the report exits 0 only when that drift is caught.
make traffic
make drift-report               # DRIFT: new categories in 'postrelease': automation
# Traces are also visible at http://localhost:6006 (project `triagewise`).

# Online LLM-as-judge (iter 5b): a stronger model re-reads a sampled half of the traced
# traffic and annotates each span correct/incorrect in Phoenix. The judge owns its LLM call —
# `make judge` is LIVE (~$0.002 per judged span; needs OPENAI_API_KEY in .env). Incremental:
# already-judged spans are skipped, so re-running without new traffic is a no-op and $0.
make judge                      # ⚠️ live, costs money
make judge-report               # verdict counts from Phoenix's store; exit 0 = judged spans exist

# Promotion loop, one manual turn (iter 6a): both prompt aliases are scored on the golden set
# (replay/$0 on derived cassettes), the strict gate compares them, and on a challenger win the
# `champion` alias swaps to its version in the registry — verified in the store, not the UI.
# Idempotent: after the swap a re-run finds no strict winner and is a no-op. Needs data/golden.jsonl
# (`uv run dvc pull`). The running triage picks the new champion up on its next call — no restart.
make promote

# Continuous-evaluation loop (iter 6b): the same promotion turn, now on a Prefect schedule
# instead of a hand. `make loop` registers a flow + interval schedule on the Compose Prefect
# server and serves it as a host runner — every LOOP_INTERVAL_SECONDS (default 60) a tick
# reruns eval -> gate -> swap (replay/$0). Long-running; Ctrl-C stops the runner. Verify the
# swap in the MLflow store, not the Prefect UI. Needs `make up` + synced prompts + golden.
LOOP_INTERVAL_SECONDS=15 make loop      # leave running; watch ticks, Ctrl-C to stop

# Control-plane dashboard (iter 7): one read-only screen at http://localhost:8501 collects the
# five lifecycle proofs (champion/challenger versions, last gate verdict, drift, cost/latency
# SLO, loop status). Comes up with `make up`; reads the stores only, writes nothing, no LLM.
open http://localhost:8501         # or just visit it in a browser after `make up`

# The CI eval gate (iter 2): promptfoo replays recorded outputs over the golden set — $0, no key.
nvm use                         # Node version pinned in .nvmrc (promptfoo needs >=22.22)
npm ci                          # project-local promptfoo, pinned by package-lock.json
make eval                       # red if the prompt regressed / outputs weren't re-recorded

make check                      # ruff + format + mypy + pytest (static gate, no LLM)
make down                       # stop MLflow + Phoenix + Prefect + dashboard
```

Make targets: `make check` (lint+types+tests), `make up`/`make down` (MLflow + Phoenix + Prefect + dashboard), `make test`,
`make fmt`, `make eval` (CI eval gate, offline replay), `make eval-build` (regenerate `eval/` assets
from the DVC-versioned golden set), `make eval-record` (⚠️ live, costs money — re-records
`eval/outputs.json`), `make cache-stats` (semantic-cache hit-rate over the SLO log),
`make traffic` (both ticket batches through triage, traced to Phoenix, replay/$0),
`make drift-report` (drift verdict from Phoenix's span store; exit 0 = drift caught),
`make judge` (⚠️ live, costs money — LLM-as-judge over sampled traced spans, incremental),
`make judge-report` (judge verdicts from Phoenix's store; exit 0 = judged spans exist),
`make promote` (champion/challenger promotion loop over the golden set, replay/$0, idempotent),
`make loop` (the promotion loop on a Prefect interval schedule — continuous evaluation, replay/$0,
long-running; Ctrl-C to stop).

The golden set (`data/golden.jsonl`, 40 labeled tickets) is DVC-versioned: `uv run dvc pull`
restores it from the local dir remote (`../triagewise-lite-dvc-remote`).

`LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit OpenAI and cost money — gated by an explicit go (CLAUDE.md rule 4).
