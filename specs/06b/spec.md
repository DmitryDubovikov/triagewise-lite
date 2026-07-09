# Итерация 06b — Prefect: continuous-evaluation петля по расписанию

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Обернуть ручную промоушен-петлю 6a в Prefect-flow с интервальным расписанием — петля
eval → gate → swap начинает крутиться сама. Нового инструмента нет: Prefect — перенос
каркаса из sentiment-mlops (правило 2 не тратится).

## 🧵 Красная нить (резюме)
> **Continuous evaluation loop (LLM-аналог continuous training)** — «Prefect-flow
> оборачивает петлю 6a + расписание: flow по расписанию гоняет re-eval → gate → swap;
> запуск с лучшим challenger → alias переезжает на новую версию (**verify в
> MLflow-реестре**)» (ROADMAP, строка 6b; north-star пункт 7).

## Новые инструменты (и минимальный объём каждого)
- **Prefect** *(перенос sentiment-mlops)* — один `@flow` поверх готового `run_promotion`
  + `flow.serve(interval=...)`. Prefect **server — третий Compose-сервис** (pinned image,
  volume): в Prefect 3 расписание исполняется строго сервером (ephemeral-режим осознанно
  без scheduler'а) — совместное решение, правит исходную формулировку «in-process serve»
  в ROADMAP/tech-decisions. Flow-runner (`make loop`) — на хосте; server-analytics off,
  клиентский стейт в `./.prefect` (gitignored).

## Done-gate (по факту существования)
`make loop` (replay, $0, LLM-сеть не нужна): serve регистрирует flow + интервальное
расписание на Compose-сервере; scheduler создаёт тик, runner исполняет его на хосте —
eval → gate → swap; на сторе, где challenger лучше champion (после демо-сброса
champion→v1, как в демо 6a), тик переезжает alias — **verify в самом MLflow-реестре**
(правило 8), не в логе flow.
**Идемпотентность:** flow — тот же `run_promotion` (6a): после swap каждый тик = no-op,
alias не дрейфует, версии не плодятся; serve пересоздаёт deployment/расписание
детерминированно (тот же name). Идемпотентность держит **сам гейт**, а не пауза расписания:
стоп runner'а расписание на сервере НЕ гасит (в Prefect 3.7.8 на Python 3.14 `Runner.astop`
из sync-хендлера сигнала не ждётся — «Pausing all deployments…» логируется, но пауза не
доезжает), поэтому неотслуженные тики копятся как Scheduled/Late. Но это безвредно: любой
накопленный тик — no-op промоушен, стор не двигает. Явную паузу расписания на стопе в скоуп
не берём (существование петли — вот ворота; не-дрейф стора уже гарантирован гейтом).
+ ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Dep `prefect>=3,<4` (pin в uv.lock); Compose-сервис `prefect` (pinned image, volume
   `prefect-data/`); `.prefect/` + `prefect-data/` в `.gitignore`.
2. `app/cli/loop.py` (транспорт): `@flow` `continuous_evaluation` — boundary-работа
   (Settings, golden, `open_registry`) → `run_promotion` → печать отчёта (как `promote`);
   `main()` зовёт `.serve(interval=Settings.loop_interval_seconds)`.
3. `Settings.loop_interval_seconds` (default 60); `make loop`: `PREFECT_API_URL` на
   Compose-сервер, `PREFECT_HOME=./.prefect`, analytics off (env внешнего тула — в
   Makefile, как PROMPTFOO_ENV); `make up` поднимает и prefect.
4. Тесты (replay): `.fn()` flow гоняет один оборот на локальном реестре — happy-path,
   swap виден в сторе, повторный тик = no-op; serve/Prefect-API в тестах не поднимаются.
5. Ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope
Prefect UI как предмет (сервер его отдаёт — ладно, но verify только через стор/API) ·
work pools / workers / deployments сверх `serve` · cron-выражения (интервала достаточно) ·
декомпозиция петли на `@task`-и (Prefect-tasks уже показаны в sentiment-mlops; здесь
героиня — петля) · live re-eval (деньги; петля живёт на derived-кассетах 6a) ·
автогенерация новых challenger-версий.
