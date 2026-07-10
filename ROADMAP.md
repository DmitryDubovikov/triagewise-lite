# triagewise-lite — ROADMAP

> Бюджет: **6–10 итераций (потолок 12)** — размер dossier, не policywise. Хребет ниже = **7 содержательных** + каркас (iter 0) + 1 опц. хвост = приземляется на **9**, с запасом до потолка.
>
> Закон ROADMAP: **колонка «🧵 красная нить» обязательна** для каждой итерации — она называет резюме-практику (из CLAUDE.md → north star), которую итерация делает демонстрируемой. Итерация без записи в этой колонке не планируется.

## Домен / фикстура (data-prep)

Вымышленный SaaS **Driftwood** (таск-трекер). Артефакты:
- **Поток тикетов** — синтетические support-тикеты (English), ~2 пачки: базовая + «пострелизная» (вводит **новую категорию** для демо дрейфа).
- **Golden-сет (~40 тикетов, размеченный)** — эталон для eval-gate. Несёт «джокеры»: двусмысленная категория, скрытый negative под вежливостью — чтобы champion/challenger-гейт различал. Версионируется DVC (iter 2).
- **Выход триажа (заморожен):** `{category, priority, sentiment, needs_human, draft_reply}`. Новых полей не добавляем (CLAUDE.md правило 3).

## Хребет итераций

| Итер | Новый инструмент | 🧵 Красная нить (резюме) | Existence-gate | Каркас откуда |
|---|---|---|---|---|
| **0** ✅ | — *(каркас)* | LLMOps-скелет заложен | репо, uv/ruff/pytest, `Settings`, slim-Compose (MLflow+sqlite+local artifacts), `llm-tiers.yaml` (cheap/mid/smart), `route("tier")` + LiteLLM SDK + кассеты, фикстура-тикеты. `route("cheap", ticket)` в `record` делает реальный nano-вызов, `replay` читает кассету; smoke зелёный; **pin-гейт (механически проверяемо): каждая модель в `llm-tiers.yaml` — датированный снапшот (имя матчит `-\d{4}-\d{2}-\d{2}$`), не плавающий алиас** (иначе облако молча дрейфует под нами) | sentiment-mlops + policywise/dossier |
| **1** ✅ | **MLflow Prompt Registry** | **Prompt-as-artifact + champion/challenger промоушен промптов** | промпт триажа залит как **версия** с alias `champion`/`challenger`; `route` грузит промпт из реестра по alias; `mlflow` показывает версии+alias (verify в сторе, не UI) | расширяет MLflow из sentiment |
| **2** ✅ | **promptfoo** | **CI eval-gate / regression testing для LLM** | golden-сет под **DVC**; promptfoo гоняет champion-промпт по golden, ассертит формат/поля; **CI job красный при регрессии** (меняю промпт «во вред» → мёрдж заблокирован) | DVC из sentiment |
| **3** ✅ | **LiteLLM access-layer** *(SDK, углублённо)* | **Cost/latency SLO (LLM FinOps) · productionized routing** | роутинг `cheap`↔`smart` как первичный chokepoint; **cost+latency на вызов** через `completion_cost` (SLO-лог); **security-гейт (механически проверяемо, правило 5):** в коде только `litellm.acompletion` и **нет** импорта `litellm.proxy`/server-процесса · `litellm.callbacks`/`success_callback`/`failure_callback` пусты · `litellm.telemetry=False` выставлен до первого вызова · версия запиннена в `pyproject.toml` + `uv.lock` | LiteLLM из policywise (там был bare-call; здесь — выпуклее) |
| **4** ✅ | — *(semantic cache поверх access-layer)* | **Productionized routing + semantic caching** | **semantic cache** поверх готового access-layer (iter 3): повтор/близкий запрос → **hit** без сетевого вызова; метрика hit-rate; промах → нормальный `route`-путь (кассеты `replay`-нейтральны) | — (надстройка над iter 3) |
| **5a** ✅ | **Arize Phoenix** | **LLM output drift / quality monitoring** | Phoenix в Compose + трейсинг триажа; вторая («пострелизная») пачка → **Phoenix показывает дрейф** распределения категорий; drift-report через Phoenix API (не UI); всё в `replay` ($0) | новый |
| **5b** ✅ | — *(Phoenix, углублённо)* | **Online evaluation / LLM-as-judge в проде** | сэмплинг трафика → **online LLM-as-judge** (`smart`-тир, live-гейт); оценки judge видны в Phoenix рядом с трейсами | — (надстройка над 5a) |
| **6a** ✅ | — *(петля вручную)* | **Champion/challenger промоушен промптов — замыкание (CD для промптов): eval → gate → swap → hot-reload** | derived-кассеты: golden × оба промпта ($0 — фабрикация из expected-меток; champion ошибается на джокерах, challenger детерминированно побеждает); `make promote` (replay): score champion vs challenger на golden → **gate** (challenger > champion?) → **swap alias `champion`** (**verify в MLflow-реестре**, не UI) → access-layer **hot-reload** (живой процесс берёт новую версию без рестарта); повторный прогон = no-op (alias не дрейфует, версии не плодятся) | — (замыкает iter 1/2) |
| **6b** ✅ | — *(Prefect)* | **Continuous evaluation loop** (LLM-аналог continuous training) | Prefect-flow оборачивает петлю 6a + расписание (Prefect server — Compose-сервис: в Prefect 3 scheduler строго серверный, ephemeral-режим его осознанно не гоняет; flow-runner `make loop` — на хосте): flow по расписанию гоняет re-eval → gate → swap; запуск с лучшим challenger → alias переезжает на новую версию (**verify в MLflow-реестре**) | Prefect из sentiment |
| **7** ✅ *(опц. хвост)* | **Streamlit** *(рендер-вехикул, не резюме-строка)* | **усиление зонтика #1 — LLMOps / lifecycle management сделан легибельным** | **control-plane dashboard** (Streamlit — отдельный Compose-сервис, pinned image): одна **read-only** панель собирает 5 живых proof'ов жизненного цикла в один экран — `champion` версия+alias (MLflow-реестр), последний gate-вердикт (`run_promotion`), drift-статус (Phoenix API), cost/latency SLO (access-layer-лог), Prefect-петля (статус/интервал). Панель **только читает** сторы, не источник истины (**verify в сторе, не в UI — правило 8**); всё на replay ($0). В `docs` явно: Streamlit — рендер, героиня — видимый control plane, новой резюме-практики нет (честность против раздувания) | — (надстройка над iter 1–6b) |

## Контроль красной нити (анти-дрейф)

- На `/iterationStart N`: спека **цитирует** строку из таблицы «🧵 красная нить» как цель итерации.
- На `/iterationClose N`: в `docs/` фиксируем, **какой резюме-ключевик стал демонстрируемым** (скрин/лог/Cypher-аналог — артефакт существования).
- Финальный showcase-README: каждая практика north-star → строка таблицы со ссылкой на доказательство (как `README.md` policywise). Стек-строка резюме собирается **только** из реально продемонстрированного.

## Сводка покрытия north-star

| Резюме-практика (CLAUDE.md) | Где демонстрируется |
|---|---|
| LLMOps / LLM lifecycle management | весь проект (зонт); **iter 7** — control-plane dashboard делает легибельным (5 proof'ов на одном экране) |
| Prompt-as-artifact + champion/challenger промоушен | iter 1, 6a |
| CI eval-gate / regression testing | iter 2 |
| Online eval / LLM-as-judge в проде | iter 5b |
| LLM output drift / quality monitoring | iter 5a |
| Cost & latency SLO (LLM FinOps) | iter 3 |
| Continuous evaluation loop | iter 6b |
| Productionized routing + semantic caching | iter 3, 4 |

## Бюджет / стоимость

Cloud-only, OpenAI через тиры. champion=`gpt-4.1-nano`, challenger/judge=`smart`. Кассеты `replay`=$0 (дефолт); `live` гейтится (спросить + оценка). Прогноз всего проекта: **~$1–5** (реалистично <$3). Снапшоты пиннить.
