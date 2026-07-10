# Итерация 07 — Streamlit control-plane dashboard

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель

Собрать 5 живых proof'ов жизненного цикла (iter 1–6b) в один read-only экран — control plane
становится **легибельным**: то, что раньше доказывалось пятью CLI-командами по разным сторам,
видно одним взглядом. Streamlit — рендер-вехикул, не резюме-строка (честность против раздувания).

## 🧵 Красная нить (резюме)

> **усиление зонтика #1 — LLMOps / lifecycle management сделан легибельным** — «control-plane
> dashboard: одна read-only панель собирает 5 живых proof'ов жизненного цикла в один экран»
> (ROADMAP, iter 7).

## Новые инструменты (и минимальный объём каждого)

- **Streamlit** — одна страница, 5 карточек-proof'ов, никакой интерактивной логики сверх
  refresh. Отдельный Compose-сервис (решение пользователя, по ROADMAP): свой Dockerfile на
  pinned python-base, deps панели пиннятся отдельным маленьким `requirements.txt` (аналог
  uv.lock для образа). Панель **только читает** сторы — не источник истины (правило 8),
  LLM-вызовов не делает (LLM-egress остаётся хост-only).

## 5 proof'ов и их источники (всё по HTTP из Compose-сети, кроме логов)

| Proof | Источник |
|---|---|
| champion версия+alias (iter 1/6a) | MLflow-реестр: `load_triage_prompt(client, alias)` для обоих alias |
| последний gate-вердикт (iter 6a) | **новый** `logs/promotions.jsonl` — `run_turn` дописывает запись за каждый gate-turn (решение пользователя: JSONL, симметрично SLO-логу) |
| drift-статус (iter 5a) | Phoenix API: `fetch_triage_spans` + `category_drift` (переиспользуем) |
| cost/latency SLO (iter 3) | `logs/llm_calls.jsonl`: агрегаты (calls, total cost, breaches, cache hit-rate) |
| Prefect-петля (iter 6b) | Prefect REST API: deployment `continuous-evaluation` (schedule) + последний flow-run |

Логи — файлы хоста → в контейнер монтируются **read-only** (`./logs`, `./app`); это
задокументированное исключение из «нет общей ФС» (шов был про artifact-path-mismatch, не про
read-only рендер). Недоступный стор → карточка деградирует с подсказкой, панель не падает.

## Done-gate (по факту существования)

`make up` поднимает панель вместе с бэкендами; `localhost:8501` показывает 5 карточек по живым
сторам. Механически: `curl localhost:8501/_stcore/health` = ok; после `make promote` в
`logs/promotions.jsonl` появляется валидная запись (jq), и карточка gate её показывает.
Идемпотентность: promotions.jsonl — append-only лог (история turn'ов), сторы панель не мутирует;
повторный `make promote` после свапа пишет `promoted:false`-запись, alias не дрейфует.
+ ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги

1. Персист gate-вердикта: `Settings.promotion_log_path`, запись в `run_turn` (общая для
   promote/loop), тест в replay.
2. Ридеры панели (`app/ui/`): 5 функций-источников, зависимости аргументами (registry-хендл /
   phoenix-клиент / settings на boundary панели); чистый парсинг — отдельно от I/O; Prefect —
   голый httpx GET (2 эндпоинта), без импорта prefect-lib в образ.
3. `app/ui/dashboard.py` — Streamlit-страница: 5 карточек + graceful degradation.
4. Dockerfile + Compose-сервис `dashboard` (pinned base, pinned deps, ro-volumes, env-URLы на
   имена сервисов), `make up` включает его; mypy-override для streamlit (в uv-env его нет).
5. Ревью-пайплайн (general + constitution → дедуп → аудитор → фиксы → `/simplify`).

## Вне scope

Никакой записи из панели (строго read-only) · auth/deploy-хлопоты · авто-refresh сверх
штатного Streamlit · host-запуск панели (решение: Compose) · новые поля триажа · новые
метрики качества (existence-gate) · правки промоушен-логики сверх append-записи.
