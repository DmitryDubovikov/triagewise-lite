# Демо / смок — Итерация 00 (каркас)

Happy-path этой итерации: скелет ставится, статический гейт зелёный, CLI триажит тикет офлайн за $0
из закоммиченной кассеты, pin-гейт реально форсит датированные снапшоты, а control-plane backend
(MLflow) поднимается и отвечает по HTTP. Все шаги копипаст-исполнимы из корня репозитория
`/Users/dd/projects/pet/triagewise-lite`. Не-live шаги ничего не стоят.

Перед началом:
```bash
cd /Users/dd/projects/pet/triagewise-lite
```

## 1. Поставить окружение

```bash
uv sync --extra dev
```
**Ожидаемо:** резолв без ошибок; в окружении появляются `litellm`, `pydantic-settings`, `pyyaml`,
`ruff`, `pytest`, `mypy`, `types-pyyaml`. `uv.lock` присутствует (версия LiteLLM запинена — 1.90.0).

## 2. Статический гейт

```bash
make check
```
**Ожидаемо:** все четыре шага зелёные —
```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 17 files already formatted
uv run mypy app                → Success: no issues found in 14 source files
uv run pytest                  → 3 passed
```

## 3. Триаж тикета через CLI — офлайн, $0 (основной путь)

```bash
uv run python -m app.cli.main DW-001
```
**Ожидаемо:** заголовок `[DW-001] cheap (replay)` и валидный `TriageResult` из кассеты:
```json
{
  "category": "account_access",
  "priority": "high",
  "sentiment": "negative",
  "needs_human": true,
  "draft_reply": "Sorry you're locked out. ..."
}
```
Сеть не трогается; модель выбрана тиром `cheap`, а не названа в коде.

## 4. Replay без кассеты падает понятно (никогда не уходит в сеть)

```bash
uv run python -m app.cli.main DW-002
```
**Ожидаемо:** не молчаливый сетевой вызов, а явная ошибка `FileNotFoundError`: «No cassette for tier
'cheap' … replay never hits the network; record it explicitly». Это и есть cost-дисциплина (правило 4)
в действии — для DW-002 кассета не записана.

## 5. Pin-гейт форсит датированные снапшоты

```bash
uv run pytest tests/test_route_replay.py::test_pin_gate_rejects_floating_alias -q
```
**Ожидаемо:** `1 passed`. Тест подсовывает `cheap: gpt-4.1-nano` (без даты) и проверяет, что загрузка
тиров падает с `ValueError` про «dated snapshot». Боевой `llm-tiers.yaml` все три тира держит датированными
(`gpt-4.1-nano-2025-04-14`, `gpt-4o-mini-2024-07-18`, `gpt-4.1-2025-04-14`).

## 6. Control-plane backend (MLflow) поднимается и отвечает

```bash
make up
docker compose ps
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/health
```
**Ожидаемо:** контейнер `mlflow` в статусе `Up`/`running`, порт хоста `5050` проброшен на `5000`
контейнера; `curl` к `http://localhost:5050/health` возвращает `200`. Хост-порт 5050, а не 5000:
на macOS порт 5000 занимает ControlCenter (AirPlay Receiver). Реестр промптов в этой итерации ещё пуст (наполняется
с iter 1) — здесь проверяем только, что бэкенд control-plane реально поднимается и доступен по HTTP, без
общей файловой системы. Остановить: `make down`.

## 7. ⚠️ Записать реальную кассету (live, стоит денег) — НЕ выполняем в церемонии

```bash
# ⚠️ live, стоит денег (правило 4): реальный вызов gpt-4.1-nano через OpenAI.
# Выставить ключ способом, который знаете только вы:
#   export OPENAI_API_KEY=sk-...        (или положить в .env)
# LLM_MODE=record uv run python -m app.cli.main DW-002
```
**Ожидаемо (если бы запускали):** реальный вызов nano, ответ печатается и сохраняется в
`cassettes/<sha256>.json`; следующий `replay` для DW-002 уже офлайн. В рамках смок-церемонии этот шаг
**пропущен** как live.
