# triagewise-lite

An **LLMOps control plane** built over a deliberately trivial fixture: triaging synthetic
support tickets for a fictional SaaS (*Driftwood*). The app is a fixture; **the ops is the
product** — prompt registry, CI eval-gates, online evaluation, drift monitoring, and a
continuous-evaluation loop. See `CLAUDE.md` (constitution) and `ROADMAP.md` (iteration backbone).

## Quickstart (through iter 5a — drift monitoring)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use
make up                         # control-plane backends: MLflow at localhost:5050, Phoenix at localhost:6006

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

# The CI eval gate (iter 2): promptfoo replays recorded outputs over the golden set — $0, no key.
nvm use                         # Node version pinned in .nvmrc (promptfoo needs >=22.22)
npm ci                          # project-local promptfoo, pinned by package-lock.json
make eval                       # red if the prompt regressed / outputs weren't re-recorded

make check                      # ruff + format + mypy + pytest (static gate, no LLM)
make down                       # stop MLflow + Phoenix
```

Make targets: `make check` (lint+types+tests), `make up`/`make down` (MLflow + Phoenix), `make test`,
`make fmt`, `make eval` (CI eval gate, offline replay), `make eval-build` (regenerate `eval/` assets
from the DVC-versioned golden set), `make eval-record` (⚠️ live, costs money — re-records
`eval/outputs.json`), `make cache-stats` (semantic-cache hit-rate over the SLO log),
`make traffic` (both ticket batches through triage, traced to Phoenix, replay/$0),
`make drift-report` (drift verdict from Phoenix's span store; exit 0 = drift caught).

The golden set (`data/golden.jsonl`, 40 labeled tickets) is DVC-versioned: `uv run dvc pull`
restores it from the local dir remote (`../triagewise-lite-dvc-remote`).

`LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit OpenAI and cost money — gated by an explicit go (CLAUDE.md rule 4).
