# Итерация 01 — MLflow Prompt Registry

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Вынуть промпт триажа из кода в **MLflow Prompt Registry** как версионируемый артефакт с алиасами `champion`/`challenger`. Триаж-поток грузит промпт **по алиасу** из реестра (а не из хардкода), формирует сообщения и зовёт `route()`. Это первая net-new практика: prompt-as-artifact + champion/challenger.

## 🧵 Красная нить (резюме)
ROADMAP, строка 1: **«Prompt-as-artifact + champion/challenger промоушен промптов»** (CD для промптов). Итерация делает демонстрируемым: промпт залит как **версия** с alias `champion`/`challenger`; поток грузит его по alias; `mlflow` показывает версии+алиасы (verify в сторе, не UI — правило 8).

## Новые инструменты (и минимальный объём каждого)
- **MLflow Prompt Registry** — расширение уже знакомого MLflow (sentiment-mlops). Минимально: один промпт `triage`, две версии (champion-сид + challenger-вариант), два алиаса, загрузка по алиасу через `MlflowClient`. Промоушен/swap алиаса — НЕ здесь (iter 6).

## Done-gate (по факту существования)
- Промпт `triage` зарегистрирован как **версия** в реестре; алиасы `champion`→v1 и `challenger`→v2 проставлены.
- Триаж-поток грузит промпт **по алиасу** (`prompts:/triage@champion`), форматирует тикетом → `messages` → `route(tier, messages)`. `route()` остаётся message-based chokepoint'ом (шов опции A, правило 6).
- Verify **в сторе** (правило 8): запрос к реестру (`get_prompt_version_by_alias`) подтверждает, что `champion`/`challenger` указывают на версии — не верим UI.
- Happy-path smoke зелёный **офлайн, $0**: triage DW-001 через champion-промпт из tmp-sqlite-реестра + закоммиченную кассету.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Dep: `mlflow>=3.1,<4` (полный, не skinny — нужен sqlite-registry-store для офлайн-тестов; это каркас sentiment, не «новый инструмент»). mypy-override для `mlflow.*`.
2. `app/persistence/prompts.py` — репозиторий реестра (единственное место, где живёт MLflow prompt-API): константы (`TRIAGE_PROMPT_NAME`, `champion`/`challenger`, чат-шаблоны champion/challenger с `{{subject}}`/`{{body}}`), `open_registry(settings)→MlflowClient` (хендл на boundary), `sync_prompts(client)` (идемпотентно заливает обе версии + алиасы, новую версию только при изменении шаблона; единый источник для теста/скрипта/автора кассеты), `load_triage_prompt(client, alias)`.
3. `app/workflow/triage_flow.py` — `triage_ticket(ticket, *, tier, client, alias=champion, settings)`: грузит промпт по алиасу, `pv.format(...)` → messages → `route`. `cli/main.py` открывает хендл и передаёт вниз. Champion-шаблон **байт-в-байт** воспроизводит iter-0 промпт (тот же ключ кассеты, $0).
4. `scripts/register_prompt.py` — заливает промпт в docker-MLflow (для демо; **не LLM**, денег не стоит), `scripts/show_prompt.py` — печатает хранимый шаблон. `scripts/author_cassette.py` — переведён на `sync_prompts`+`pv.format()` (единый путь сообщений), кассета DW-001 перегенерирована офлайн. Тесты (tmp-sqlite реестр через фикстуру): happy-path replay + champion/challenger-алиасы существуют в сторе + идемпотентность `sync_prompts`; pin-gate тест сохранён.
5. Ревью-пайплайн (general + constitution → auditor → фиксы) → `/simplify`.

## Вне scope
Промоушен/swap алиаса champion↔challenger (iter 6) · promptfoo/DVC golden-set (iter 2) · cost/latency (iter 3) · Phoenix (iter 5) · новые выходные поля · точность триажа (existence-gate) · live LLM-прогон (правило 4: кассета `replay` уже есть). Champion-промпт не «улучшаем» — переносим iter-0 как есть.
