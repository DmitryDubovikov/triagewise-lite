# Итерация 00 — Каркас (LLMOps-скелет)

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Заложить скелет control-plane: репозиторий, тулчейн (uv/ruff/pytest), `Settings`, slim-Compose с MLflow, `llm-tiers.yaml`, `route("tier")` поверх LiteLLM-SDK с кассетами и фикстуру-тикеты. **Нового инструмента нет** — это перенос каркаса из sentiment-mlops + policywise/dossier (правило 2). Цель — чтобы все швы (правило 6) и дисциплина LiteLLM (правило 5) встали на места, а `route("cheap", ticket)` поехал в `replay` офлайн за $0.

## 🧵 Красная нить (резюме)
ROADMAP, строка 0: **«LLMOps-скелет заложен»** — фундамент под все net-new практики (prompt-registry, eval-gate, online-eval, continuous-evaluation). Сама по себе строчка резюме не закрывает; делает демонстрируемыми остальные.

## Новые инструменты (и минимальный объём каждого)
- **Нет.** Перенос каркаса 1:1: uv/ruff/pytest, pydantic-settings (`Settings`), Docker Compose (только MLflow), LiteLLM-SDK bare-call, tier-router, кассеты record/replay.

## Done-gate (по факту существования)
- Репо инициализировано (`git init`), `.gitignore`, тулчейн `uv` + `ruff` + `pytest`.
- `Settings` (`app/config.py`) — единственный доступ к env (`LLM_MODE`, `TRIAGE_TIER`, `JUDGE_TIER`, ключи/base_url, пути, `MLFLOW_TRACKING_URI`).
- slim `docker-compose.yml`: MLflow server (sqlite backend-store + local artifacts, **`--serve-artifacts`**, порт 5000). Только этот сервис.
- `llm-tiers.yaml` с `cheap`/`mid`/`smart`. **Pin-гейт (механически):** каждая модель матчит `-\d{4}-\d{2}-\d{2}$` — датированный снапшот, не плавающий алиас.
- `route("tier", ...)` — единый chokepoint поверх LiteLLM SDK; `replay` читает кассету офлайн (никогда не сеть), `record`/`live` гейтятся. Дисциплина LiteLLM (правило 5): SDK-only, ленивый импорт, телеметрия off, callbacks пусты, версия + uv.lock.
- Фикстура: `fixtures/tickets.jsonl` — синтетические Driftwood support-тикеты (English), пара «джокеров» (двусмысленная категория / скрытый negative).
- **Smoke зелёный:** `route("cheap", ticket)` в `replay` возвращает распарсенный `TriageResult` из закоммиченной кассеты, без сети.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Тулчейн+репо: `pyproject.toml` (deps + ruff/pytest), `git init`, `.gitignore`, `.env.example`, минимальный `README.md`.
2. `Settings` + `llm-tiers.yaml` (датированные снапшоты) + загрузчик тиров.
3. `app/llm/`: кассеты (ключ = sha256 от `{model, messages}`, файл-на-ключ) + `route()` (replay/record/live, дисциплина LiteLLM). `domain/triage.py`: схема `TriageResult` (замороженные поля) + парсер. Тонкий `cli/`.
4. Фикстура-тикеты + **офлайн** скрипт-автор кассеты (`scripts/author_cassette.py`, чистый, без сети — фабрикует валидный triage-ответ через тот же `cassette_key()`); закоммитить кассету. Happy-path тест `route("cheap", ...)` в `replay`.
5. Ревью-пайплайн (general + constitution → auditor → фиксы) → `/simplify`.

## Вне scope
Prompt Registry (iter 1), promptfoo/DVC golden-set (iter 2), access-layer cost/latency (iter 3), кэш (iter 4), Phoenix (iter 5), Prefect (iter 6). Новые выходные поля. Live LLM-прогон без явной просьбы (правило 4). Точность триажа.
