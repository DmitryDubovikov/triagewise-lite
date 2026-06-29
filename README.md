# triagewise-lite

An **LLMOps control plane** built over a deliberately trivial fixture: triaging synthetic
support tickets for a fictional SaaS (*Driftwood*). The app is a fixture; **the ops is the
product** — prompt registry, CI eval-gates, online evaluation, drift monitoring, and a
continuous-evaluation loop. See `CLAUDE.md` (constitution) and `ROADMAP.md` (iteration backbone).

## Quickstart (iter 0 — scaffold)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use
make up                         # control-plane backend (MLflow) at localhost:5050

# Triage one ticket — replay mode is offline and $0 (default).
uv run python -m app.cli.main DW-001

make check                      # ruff + format + mypy + pytest (static gate, no LLM)
make down                       # stop MLflow
```

Make targets: `make check` (lint+types+tests), `make up`/`make down` (MLflow), `make test`, `make fmt`.

`LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit OpenAI and cost money — gated by an explicit go (CLAUDE.md rule 4).
