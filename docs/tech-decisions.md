# Решения по стеку

> 🎯 **Цель проекта:** минимальными затратами — максимальное знакомство с инструментами **LLMOps-жизненного цикла**. Existence-gate, не accuracy-gate.

Что взяли в ядро, что отложили, что выкинули — и почему. Зафиксировано на старте; не пересматривать без явного решения. triagewise-lite — **четвёртый «lite»-сиблинг** (после policywise / dossier / sentiment-mlops): берёт ось, которую они не покрыли (см. ниже).

## Почему отдельный проект, а не итерация существующих

У пользователя уже три проекта: **policywise-lite** (пассивный RAG-QA: vector/hybrid/rerank, eval, observability), **dossier-lite** (активный агент: crew, browser, граф, chat-UI), **sentiment-mlops** (классический supervised MLOps: MLflow/Prefect/DVC/Compose). Непокрытой осью остаётся **LLMOps как операционный жизненный цикл** — не «ещё одно LLM-приложение» (это продублировало бы policywise/dossier), а **control plane** над промптами/моделями: версионирование, champion/challenger-промоушен, CI eval-gate, online-eval, drift-мониторинг, continuous-evaluation петля.

**Сдвиг сути:** policywise/dossier — это LLM-*приложения* с ops-гигиеной сбоку; triagewise — там, где **ops и есть продукт** («приложение — фикстура, ops — продукт»). Это делает новые инструменты органичными, а не приклеенными: «жизненный цикл промпта» тянет реестр, «не сломать прод промптом» — eval-gate, «промпт дрейфует» — мониторинг, «автоматически держать лучший» — continuous-evaluation петлю.

**Каркас переиспользуем, а не изобретаем.** Машинерия sentiment-mlops переносится почти 1:1: MLflow registry → реестр промптов, Prefect → расписание eval, DVC → версия golden-сета, FastAPI-сервинг → access-layer. LiteLLM/MLX/кассеты/router — из policywise. Это **каркас**, не «новые инструменты» (правило 2).

## Красная нить (резюме) — см. `CLAUDE.md` north-star

Net-new для портфолио — **практики** lifecycle-автоматизации (LLMOps, prompt-as-artifact, champion/challenger промоушен, CI eval-gate, online LLM-as-judge, drift-мониторинг, LLM FinOps, continuous-evaluation) и **3 инструмента**: promptfoo, MLflow Prompt Registry, Arize Phoenix. Всё остальное (LiteLLM, MLX, eval-фреймворки, Langfuse, MLflow-база) **уже в резюме** от трёх проектов — здесь оно каркас, не герой.

## В ядре

| Инструмент | Зачем минимально |
|---|---|
| uv | менеджер пакетов и раннер — клей, не предмет изучения |
| Docker Compose | поднять MLflow (backend-store + artifacts); slim, только нужное |
| Pydantic + pydantic-settings | валидированный structured triage-output + единый `Settings` |
| OpenAI (cloud, тиры) | LLM провайдер; тиры `cheap`/`mid`/`smart` в `llm-tiers.yaml` |
| LiteLLM SDK | OpenAI-совместимый клиент — **перенос policywise**, строго SDK-only |
| tier-router + кассеты | **перенос policywise**: `route("tier")` + record/replay (детерминизм, $0) |
| MLflow Prompt Registry | промпт как версионируемый артефакт + champion/challenger aliases (iter 1) |
| promptfoo | CI eval-gate: регрессия промпта блокирует мёрдж (iter 2) |
| DVC | версионирование golden-сета — **перенос sentiment** (iter 2) |
| Arize Phoenix | online LLM-as-judge + drift/quality-мониторинг (iter 5) |
| Prefect | расписание continuous-evaluation петли + промоушен — **перенос sentiment** (iter 6) |

## Что в Docker, что на хосте (граница исполнения)

Принцип: **Docker держит только stateful-сервисы control-plane'а, которые должны быть «подняты» и хранить состояние между прогонами. Всё остальное — на хосте.** Хост-baseline неизбежно = Python + uv (приложение — фикстура под активной разработкой, edit-run цикл, кассеты/DVC по рабочему дереву → докеризовать сам dev-app явно хуже). Правило клаттера: **«клаттер» = новый рантайм/демон на хосте, а не библиотека в существующем окружении.** Поэтому всё Python-based — это просто deps в одном uv-env, не засорение. На равных Docker vs хост выигрывает Docker; но не тащим Docker туда, где он явно хуже.

**В Docker Compose (сервисы — «бэкенды control plane»):**
- **MLflow server** (iter 0) — tracking + Prompt Registry. Backend-store = sqlite (volume), артефакты = local dir (volume), запуск с **`--serve-artifacts`** → клиенты ходят к реестру **только по HTTP**, без общей ФС.
- **Arize Phoenix** (iter 5) — online-observability + drift-дашборд; персистит трейсы между прогонами. Симметрично MLflow (сервис + UI).

**На хосте:**
- **Приложение** (`app/` CLI/UI) + **все Python-deps в одном uv-env**: LiteLLM SDK (lib in-process; Proxy запрещён правилом 5 → сервиса нет), **Prefect** (iter 6 — lib, flow триггерю in-process вручную, не dockerized-сервер), **DVC**, ruff, pytest. Это deps, не рантаймы → не клаттер; Docker тут добавил бы вес ради ничего.
- **promptfoo** (iter 2) — Node-CLI. Пакет держим **проектно-локально** (`package.json` + `npm install` → `./node_modules`, пиннится `package-lock.json`, аналог `.venv`/`uv.lock`). Node-рантайм уже стоит на машине (nvm) → отдельного рантайма не добавляем, клаттер-аргумента нет → Docker не даёт выгоды, только проводку (volumes/ключ/сеть к MLflow). В CI — эфемерный GH-runner, Node просто есть.

**Граница (шов исполнения):**
- Хост-процессы общаются с Docker-сервисами **только по `localhost:<port>` HTTP**; URL'ы — в `Settings`. **Нет общей файловой системы** между хостом и контейнерами (поэтому MLflow `--serve-artifacts`) — иначе path-mismatch (`./mlruns` на хосте vs `/mlflow` в контейнере).
- **Исходящий LLM-egress идёт только из хост-процессов** (приложение через `route()`, плюс promptfoo и Phoenix-judge со своими вызовами — гейтятся как live). Контейнеры в сеть к OpenAI не ходят. Blast radius — один контролируемый вызов (правило 5).

## Развилки — как решили

- **LLMOps-приложение vs LLMOps-control-plane → control plane.** «Ещё один RAG/агент» продублировал бы policywise/dossier. Новизна и резюме-ценность — в *операционном жизненном цикле*, а не в самом LLM-приложении. Поэтому LLM-задача нарочно тривиальна (триаж тикетов), а сложность — в registry/gate/promotion/monitoring.

- **Cloud-only (OpenAI) vs локальный MLX → cloud-only; MLX в опц. хвост.** Деньги тут не аргумент: весь проект ≈ **$1–5** на `gpt-4.1-nano` (кассеты держат расход снизу). Решает **хлопотность**: локальный `mlx_lm.server` — это host-сервис, скрипты, RAM-давление; убираем его → проект легче (бюджет 6–10 итераций, не policywise). MLX уже в резюме от policywise — отложив его, ничего не теряем. Cost-aware routing всё равно демонстрируется на облачных тирах `cheap`↔`smart`. # dl-lite: MLX local champion (on-device/privacy-флавор) — опциональный хвост.

- **Тиры заложены сразу, переключение — рантайм-флаг.** `cheap`=`gpt-4.1-nano` (champion по умолчанию, $0.10/$0.40 за 1M, самая дешёвая на прямом API июнь-2026), `mid`=`gpt-4o-mini` (лёгкий шаг вверх, если nano не устроит), `smart`=сильная (`gpt-5`/`gpt-4.1`, challenger + LLM-as-judge). Маппинг тир→модель — единственное место в `llm-tiers.yaml`; роли резолвятся через `Settings` (`TRIAGE_TIER`, `JUDGE_TIER`). Сменить nano→mid = одна строка env, не правка кода. **Снапшоты пиннить** — облако молча дрейфует, что иронично вредно для проекта *про* дрейф; пиннинг даёт воспроизводимость.

- **LiteLLM строго SDK, НИКОГДА Proxy (security, красная линия).** LiteLLM имеет реальный след инцидентов безопасности (CVE Proxy-сервера + телеметрия). Повторяем дисциплину policywise: один **голый** `acompletion`, без callbacks/success_callback (каждый — канал утечки), **телеметрия off**, ленивый импорт, **пиннинг версии + uv.lock**, base_url/ключи только через `Settings`. Цель — «чтобы никто ничего не украл с компьютера»: blast radius = один исходящий вызов, который мы контролируем. Это снимает «LiteLLM gateway» из скопа — gateway = запрещённый Proxy; на резюме идёт «LiteLLM-SDK **access layer**». # dl-lite: managed LiteLLM Proxy под хардненингом — намеренно НЕ делаем.

- **promptfoo vs DeepEval/Ragas → promptfoo, и eval — НЕ герой.** policywise уже отработал DeepEval/Ragas (offline-eval как предмет). Здесь eval — **инструмент гейта в CI** (регрессия промпта валит мёрдж), а не исследовательский вклад; иначе строчка дублирует policywise. promptfoo заточен ровно под это (prompt-тесты + ассерты в CI), его в портфолио нет. **promptfoo владеет своими LLM-вызовами** (собственный provider-конфиг) — гейтится как live, аналогично исключению CrewAI в dossier.

- **MLflow Prompt Registry vs Langfuse prompt-management → MLflow.** MLflow-база уже знакома по sentiment-mlops, а Prompt Registry — её *новая фича* (промпт-как-артефакт, версии, aliases) → расширяем известное, переиспользуя champion/challenger-машинерию sentiment. Langfuse prompt-management дал бы дубль (Langfuse уже в policywise).

- **Online-observability: Arize Phoenix (а не Evidently-LLM / Langfuse).** Langfuse уже в резюме от policywise — брать его = не «новый инструмент». Phoenix — самый узнаваемый open-source LLM-observability/eval-бренд, нативно держит online LLM-as-judge + drift-дашборды. Evidently-LLM — отклонённая альтернатива (ближе к классическому ML-monitoring, чем к LLM-специфике). # dl-lite: Evidently как доп-слой data-drift — апгрейд по желанию.

- **champion/challenger для ПРОМПТОВ, не для моделей.** Классический MLflow champion/challenger из sentiment был про версии модели. Здесь та же машинерия применяется к **промптам** (+ паре промпт×тир) — это и есть «CD для промптов», net-new практика. Модель меняется тиром (`llm-tiers.yaml`), промпт — версией в реестре.

- **Continuous evaluation вместо continuous training.** В sentiment петля была train→eval→promote. У LLM обучать нечего (cloud) — петля становится **eval→gate→promote**: Prefect по расписанию re-eval challenger на golden, gate (побил champion?), swap alias, access-layer hot-reload. Прямой LLM-аналог CT.

- **Домен — фикстура (триаж тикетов вымышленного SaaS Driftwood).** Прямая LLM-эволюция домена sentiment-mlops (классификация текста). Тикет → `{category, priority, sentiment, needs_human, draft_reply}`. Golden-сет несёт «джокеры» (двусмысленная категория, скрытый negative), чтобы champion/challenger-гейт имел что различать; вторая пачка тикетов («релиз продукта» → новая категория) даёт дрейф для мониторинга. English product, Russian docs. Ширину заморозить: один продукт, без новых выходных полей.

## Сквозные конвенции (рубрика для ревью)

- **`Settings` — единственный доступ к env** (`app/config.py`, pydantic-settings). Никаких `os.environ`/`os.getenv` вразнобой. base_url/ключи/тиры/режимы — только через него.
- **Единый LLM-chokepoint — `route("tier", ...)`.** Все *собственные* LLM-вызовы приложения идут через роутер (маппинг тир→модель в `llm-tiers.yaml`). Прямой `openai`/`litellm` SDK в модуле мимо `route()` — нарушение. **Исключение:** promptfoo и Phoenix-judge владеют своими вызовами (внешние харнессы) — гейтятся как live.
- **Кассеты — режим по умолчанию `replay` ($0, офлайн, никогда не бьёт в сеть).** `record`/`live` = деньги, гейтятся явным go (правило 4). Нет кассеты в `replay` → понятная ошибка, молча в `record` не уходим.
- **Реестр-хендл (MLflow client) открывается на транспортном boundary** и передаётся вниз аргументом. Запись версий/aliases промптов — на boundary, не в domain/workflow-нодах.
- **Слои:** `domain/` не импортирует `app/*`; поток строго `transport → workflow → domain/persistence`; вызовы между слоями — обычные функции, зависимости аргументами (без DI-фреймворка).
- **Тесты — в `replay` по умолчанию;** один happy-path на done-gate достаточно (existence-gate). Live-прогоны (триаж вживую, promptfoo live, Phoenix online, запись кассет) в CI не гоняются.

## Что осознанно НЕ делаем

fine-tuning / LoRA (отдельная территория, train-инфра) · vector-RAG (policywise) · мульти-агент (dossier) · **LiteLLM Proxy/gateway** (security) · prod-deploy / k8s / автоскейл · новые выходные поля в триаже · eval-фреймворк как исследовательский вклад · собственные метрики качества (existence-gate, не accuracy) · локалку как обязательный путь (опц. хвост).
