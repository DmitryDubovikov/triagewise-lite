# triagewise-lite

An **LLMOps control plane** built over a deliberately trivial fixture: triaging synthetic
support tickets for a fictional SaaS (*Driftwood*). The app is a fixture; **the ops is the
product** — prompt registry, CI eval-gates, online evaluation, drift monitoring, and a
continuous-evaluation loop. See `CLAUDE.md` (constitution) and `ROADMAP.md` (iteration backbone).

## Quickstart (through iter 1 — prompt registry)

```bash
uv sync --extra dev
cp .env.example .env            # defaults are fine for offline use
make up                         # control-plane backend (MLflow) at localhost:5050

# Register the triage prompt as a versioned artifact with champion/challenger aliases.
# Talks to the registry only — no LLM call, costs nothing.
uv run python -m scripts.register_prompt

# Triage one ticket — loads the champion prompt by alias; LLM is offline/$0 in replay (default).
uv run python -m app.cli.main DW-001

make check                      # ruff + format + mypy + pytest (static gate, no LLM)
make down                       # stop MLflow
```

Make targets: `make check` (lint+types+tests), `make up`/`make down` (MLflow), `make test`, `make fmt`.

`LLM_MODE` is `replay` by default (reads committed cassettes, never the network).
`record`/`live` hit OpenAI and cost money — gated by an explicit go (CLAUDE.md rule 4).
