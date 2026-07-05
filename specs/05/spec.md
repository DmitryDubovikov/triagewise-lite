# Итерация 05 — Arize Phoenix: трейсинг + drift-мониторинг (5a)

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель

Ввести **Arize Phoenix** как online-observability сервис control plane: триаж-трафик трейсится в Phoenix, а вторая («пострелизная») пачка тикетов делает дрейф распределения видимым. Итерация 5 расщеплена (решение пользователя): **5a — трейсинг + drift** (эта, целиком в `replay`, $0); **5b — online LLM-as-judge** (следующая, там концентрируются live-деньги).

## 🧵 Красная нить (резюме)

ROADMAP #5: «**Online evaluation / LLM-as-judge в проде · drift / quality monitoring**» — 5a делает демонстрируемой половину «**LLM output drift / quality monitoring**»; половина «online LLM-as-judge» уходит в 5b.

## Новые инструменты (и минимальный объём каждого)

- **Arize Phoenix** — контейнер в Compose (пин `arizephoenix/phoenix:17.17.0`, volume-персистенс, симметрично MLflow). На хосте только лёгкая обвязка: `arize-phoenix-otel==0.16.1` (спаны) и `arize-phoenix-client==2.12.0` (verify store) — это проводка Phoenix, не отдельные инструменты.

## Done-gate (по факту существования)

- `make up` поднимает Phoenix рядом с MLflow; batch-прогон **обеих** пачек в `replay` ($0) пишет спаны с атрибутами `{batch, category, priority, sentiment, needs_human, tier}` (model/mode осознанно нет: спан их только предсказывал бы, ground truth — SLO-лог iter 3).
- `make drift-report` — запрос к **Phoenix API, не UI** (правило 8): печатает распределение категорий по пачкам; новая категория присутствует только в пострелизной → дрейф пойман механически.
- Phoenix UI показывает трейсы обеих пачек (артефакт-скрин для docs при close).
- **Идемпотентность:** трейсы append-only; повторный batch-прогон добавляет спаны, но drift-report агрегирует распределение **по batch-атрибуту** → вердикт стабилен на повторных прогонах.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги

1. **Compose + Settings:** сервис `phoenix` (пин, volume); `Settings`: `phoenix_enabled` (default **off** — CI/тесты байт-в-байт как iter 4), `phoenix_endpoint`, `phoenix_project`.
2. **Трейсинг:** init на транспортном boundary (аналог registry-хендла); один спан на триаж в workflow через глобальный OTel-tracer (no-op, когда off). Никаких litellm-callbacks (правило 5) — спан наш, вокруг `triage_ticket`.
3. **Фикстура дрейфа:** `fixtures/tickets_postrelease.jsonl` (~10 тикетов, релиз «Automations» → новая категория `automation`); реплаи выносятся в файл-фикстуру; `author_cassette --all` авторит кассеты обеих пачек офлайн. `# dl-lite: реплаи сфабрикованы (формат-валидны) → апгрейд: LLM_MODE=record живьём`.
4. **Batch-транспорт:** `python -m app.cli.batch <tickets.jsonl> --batch <label>` — тонкий адаптер: цикл по тикетам → `triage_ticket` (replay).
5. **Drift-report:** `scripts/drift_report.py` + `make drift-report` (phoenix-client, распределение категорий по batch-атрибуту).
6. Ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope

Online LLM-as-judge и сэмплинг (→ 5b) · live-прогоны любого рода · embedding/семантический drift (категориального распределения достаточно — existence-gate) · Evidently · новые выходные поля · алёртинг по дрейфу.
