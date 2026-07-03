# Итерация 03 — LiteLLM access-layer: cost/latency SLO

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель

Углубить LiteLLM-каркас до **access-layer**: каждый вызов через `route()` получает
per-call **cost (через `litellm.completion_cost`) + latency**, пишется в SLO-лог, а
дисциплина правила 5 (SDK-only, no Proxy, no callbacks, telemetry off, pin) становится
**механически проверяемым** тестом, а не строчкой в доке.

## 🧵 Красная нить (резюме)

> **Cost/latency SLO (LLM FinOps) · productionized routing** — роутинг `cheap`↔`smart`
> как первичный chokepoint; cost+latency на вызов через `completion_cost` (SLO-лог);
> security-гейт (механически проверяемо, правило 5).

## Новые инструменты (и минимальный объём каждого)

- **LiteLLM углублённо** *(не новый — каркас policywise, здесь выпуклее)*:
  `completion_cost` по ответу + SLO-лог. Никаких Router/Proxy/fallback-фич LiteLLM.

## Решённые развилки (обсуждено)

- SLO-лог → **JSONL-файл** (`logs/llm_calls.jsonl`, путь в `Settings`) + строка в stderr.
- Cost в replay → **кассета несёт записанный cost**: `record` сохраняет `usage`+`cost_usd`
  в кассету, `replay` логирует его с `cost_source=cassette` (фактическая трата $0);
  кассеты без cost → `0.0`.
- SLO-пороги → **глобально в `Settings`** (`SLO_MAX_COST_USD`, `SLO_MAX_LATENCY_MS`);
  превышение = WARNING в лог, вызов **не** валится.
- Один **record-прогон** (~$0.01, отдельный явный go перед запуском): перезаписать
  cheap-кассету + записать smart-кассету → демо cheap↔smart и ненулевой cost офлайн.

## Done-gate (по факту существования)

1. Прогон CLI в `replay` добавляет в `logs/llm_calls.jsonl` запись
   `{ts, tier, model, mode, latency_ms, cost_usd, cost_source, slo_breaches}`; то же в stderr.
2. `TRIAGE_TIER=smart` в `replay` проходит по smart-кассете — роутинг cheap↔smart
   демонстрируется рантайм-флагом, $0.
3. **Security-гейт** — pytest, механически проверяющий: в `app/` litellm-вызов только
   `acompletion` и нет `litellm.proxy`/server; callbacks/success/failure пусты и
   `telemetry=False` выставлены до первого вызова; `import app.llm.router` не тянет
   `litellm` в `sys.modules` (ленивость); пин в `pyproject.toml` + `uv.lock`.
4. Ревью-пайплайн чист (CRITICAL/BUG = 0).

Идемпотентность: стор не мутируется (реестр не трогаем); лог append-only — повторный
прогон добавляет строку, это заявленное поведение.

## Шаги

1. `app/llm/slo.py`: `CallRecord` (pydantic) + чистая `check_slo()` + `log_call()`
   (JSONL append + stderr). `Settings`: `slo_max_cost_usd`, `slo_max_latency_ms`,
   `llm_log_path`.
2. `router.py`: замер latency вокруг обоих путей; в record/live — cost из
   `completion_cost`, запись `usage`+`cost_usd` в кассету; в replay — cost из кассеты.
   Сигнатура `route() -> str` не меняется, лог — side effect access-layer.
3. `tests/test_litellm_discipline.py` (security-гейт) + happy-path на SLO-лог в `replay`.
4. Record-прогон по явному go (~$0.01): cheap + smart кассеты с реальным cost.
5. Ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope

Semantic cache (iter 4) · Phoenix (iter 5) · per-tier бюджеты в `llm-tiers.yaml` ·
retry/fallback/Router-политики LiteLLM · агрегация cost по прогону/дашборд ·
изменение сигнатуры `route()` · новые поля триажа.
