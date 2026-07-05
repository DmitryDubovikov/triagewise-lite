# Итерация 05b — Phoenix online LLM-as-judge

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель

Замкнуть вторую половину расщеплённой итерации 5: **online evaluation поверх прод-трафика**. Отдельный judge-job тянет triage-спаны из Phoenix, детерминированно сэмплирует часть, судит качество триажа `smart`-тиром (LLM-as-judge через `phoenix.evals` — углубление Phoenix, не новый инструмент) и пишет оценки обратно как **span-annotations**, видимые в Phoenix рядом с трейсами.

## 🧵 Красная нить (резюме)

ROADMAP #5b: «**Online evaluation / LLM-as-judge в проде** — сэмплинг трафика → online LLM-as-judge (`smart`-тир, live-гейт); оценки judge видны в Phoenix рядом с трейсами».

## Новые инструменты (и минимальный объём каждого)

- **Arize Phoenix, углублённо** — две новые грани: `arize-phoenix-evals` (`llm_classify` + классификационный шаблон correct/incorrect, судит тройку category/priority/sentiment против текста тикета) и **annotations API** клиента (запись оценки на спан + чтение обратно). Judge **владеет своим вызовом** (исключение tech-decisions, как promptfoo) → **live-гейт**; модель судьи всё равно резолвится из `llm-tiers.yaml` через `JUDGE_TIER` (`resolve_model`), никакого имени модели в коде.

## Done-gate (по факту существования)

- `make judge` — **live-гейт (≈$0.03–0.10: ~10 сэмплированных спанов × gpt-4.1), гоняется только по явному go**: тянет triage-спаны из Phoenix API, сэмплирует по `JUDGE_SAMPLE_RATE` (детерминированно от `ticket_id`), судит, пишет annotation `{label: correct|incorrect, score, explanation}` на каждый осуждённый спан.
- **Verify the store, не UI (правило 8):** `make judge-report` — запрос к Phoenix API печатает оценки judge по спанам (счётчики label'ов); UI-скрин «оценка рядом с трейсом» — артефакт при close.
- **Идемпотентность:** повторный `make judge` пропускает уже осуждённые спаны (инкрементальный оценщик) → no-op и $0 без нового трафика.
- Тесты/CI — без сети и без `phoenix.evals`: glue judge-flow тестируется с инжектированным фейк-judge'ем; live в CI не гоняется. `PHOENIX_ENABLED=0`-пути байт-в-байт как 5a.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги

1. **Deps + Settings:** `arize-phoenix-evals` (пин в `pyproject` + `uv.lock`, ленивый импорт только в judge-пути), `Settings.judge_sample_rate` (default 0.5), имя аннотации-константа.
2. **Domain:** чистые функции — детерминированный сэмпл (hash от `ticket_id` против rate) и отбор ещё-не-осуждённых спанов; без I/O.
3. **Workflow `judge_flow`:** fetch spans (Phoenix client) → filter (domain) → judge (`llm_classify`, модель из `JUDGE_TIER`) → write annotations; judge-раннер — инжектируемая зависимость (тестируется фейком).
4. **Транспорт:** `python -m app.cli.judge` (тонкий адаптер, симметрично `batch`) + `make judge` / `make judge-report` (`scripts/judge_report.py`, симметрично `drift_report`).
5. Ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope

Judge через `route()`/кассеты (решение пользователя: харнесс `phoenix.evals`) · инлайн-оценка в triage-пути · агрегированные метрики качества / алёртинг по оценкам · Prefect-расписание петли (iter 6) · драфт-reply в скоуп судьи · новые выходные поля.
