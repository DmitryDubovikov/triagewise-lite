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
| **2** | **promptfoo** | **CI eval-gate / regression testing для LLM** | golden-сет под **DVC**; promptfoo гоняет champion-промпт по golden, ассертит формат/поля; **CI job красный при регрессии** (меняю промпт «во вред» → мёрдж заблокирован) | DVC из sentiment |
| **3** | **LiteLLM access-layer** *(SDK, углублённо)* | **Cost/latency SLO (LLM FinOps) · productionized routing** | роутинг `cheap`↔`smart` как первичный chokepoint; **cost+latency на вызов** через `completion_cost` (SLO-лог); **security-гейт (механически проверяемо, правило 5):** в коде только `litellm.acompletion` и **нет** импорта `litellm.proxy`/server-процесса · `litellm.callbacks`/`success_callback`/`failure_callback` пусты · `litellm.telemetry=False` выставлен до первого вызова · версия запиннена в `pyproject.toml` + `uv.lock` | LiteLLM из policywise (там был bare-call; здесь — выпуклее) |
| **4** | — *(semantic cache поверх access-layer)* | **Productionized routing + semantic caching** | **semantic cache** поверх готового access-layer (iter 3): повтор/близкий запрос → **hit** без сетевого вызова; метрика hit-rate; промах → нормальный `route`-путь (кассеты `replay`-нейтральны) | — (надстройка над iter 3) |
| **5** | **Arize Phoenix** | **Online evaluation / LLM-as-judge в проде · drift / quality monitoring** | сэмплинг трафика → **online LLM-as-judge** (`smart`-тир); вторая («пострелизная») пачка → **Phoenix-дашборд показывает дрейф** распределения/качества | новый |
| **6** | — *(петля замыкается, Prefect)* | **Continuous evaluation loop** (LLM-аналог continuous training) | Prefect по расписанию: re-eval `challenger` на golden → **gate** (challenger > champion?) → **swap alias `champion`** → access-layer **hot-reload**. Запускаю flow с лучшим challenger → alias переезжает на новую версию (**verify в MLflow-реестре**) | Prefect из sentiment |
| **7** *(опц. хвост)* | на выбор | усиление красной нити | guardrails-фреймворк / feedback-collection UI (Chainlit reuse) / cost-budget alerting / MLX local tail | — |

## Контроль красной нити (анти-дрейф)

- На `/iterationStart N`: спека **цитирует** строку из таблицы «🧵 красная нить» как цель итерации.
- На `/iterationClose N`: в `docs/` фиксируем, **какой резюме-ключевик стал демонстрируемым** (скрин/лог/Cypher-аналог — артефакт существования).
- Финальный showcase-README: каждая практика north-star → строка таблицы со ссылкой на доказательство (как `README.md` policywise). Стек-строка резюме собирается **только** из реально продемонстрированного.

## Сводка покрытия north-star

| Резюме-практика (CLAUDE.md) | Где демонстрируется |
|---|---|
| LLMOps / LLM lifecycle management | весь проект (зонт) |
| Prompt-as-artifact + champion/challenger промоушен | iter 1, 6 |
| CI eval-gate / regression testing | iter 2 |
| Online eval / LLM-as-judge в проде | iter 5 |
| LLM output drift / quality monitoring | iter 5 |
| Cost & latency SLO (LLM FinOps) | iter 3 |
| Continuous evaluation loop | iter 6 |
| Productionized routing + semantic caching | iter 3, 4 |

## Бюджет / стоимость

Cloud-only, OpenAI через тиры. champion=`gpt-4.1-nano`, challenger/judge=`smart`. Кассеты `replay`=$0 (дефолт); `live` гейтится (спросить + оценка). Прогноз всего проекта: **~$1–5** (реалистично <$3). Снапшоты пиннить.
