# triagewise-lite — рабочая конституция

> 🎯 **Цель проекта:** добавить в резюме то, чего нет в трёх предыдущих, — **LLMOps как операционный жизненный цикл LLM**. Минимальными затратами, один новый инструмент на итерацию, проверка по факту существования инструмента, **не по точности** триажа.

Это учебный pet-проект — **четвёртый «lite»-сиблинг**. Семья и оси:

- **policywise-lite** — *пассивный QA по статике* (vector/hybrid/rerank, eval, observability).
- **dossier-lite** — *активный агент, добывающий знание* (crew, browser, граф, chat-UI).
- **sentiment-mlops** — *классический supervised MLOps* (донор каркаса: MLflow/Prefect/DVC/Compose).
- **triagewise-lite** — **не приложение, а control plane: эксплуатация жизненного цикла LLM.**

**Сдвиг сути (держим осознанно).** policywise и dossier — это *LLM-приложения с ops-гигиеной сбоку*. triagewise — там, где **ops и есть продукт**. Девиз: **«приложение — фикстура, ops — продукт».** Это наследник симметрии sentiment-mlops (модель тривиальна) — но теперь тривиальность LLM-задачи *осознанна и задокументирована* (existence-gate), а машинерия жизненного цикла — героиня, а не декорация. Именно этот сдвиг заставляет новые инструменты возникать по делу.

---

## 🧵 Красная нить: что этот проект кладёт в резюме (north star)

> Это **главная цель и инвариант**. Каждая итерация обязана продвинуть хотя бы один пункт отсюда и не дать ему издрейфовать. Если итерация не двигает красную нить — она не нужна. Existence-gate (правило 1) проверяет в т.ч. «резюме-ключевик стал демонстрируемым».

**Net-new ПРАКТИКИ (главное золото — их нет ни в одном из трёх проектов):**

1. **LLMOps / LLM lifecycle management** — зонтичный термин, которого у пользователя сейчас нет вообще.
2. **Prompt-as-artifact + champion/challenger промоушен промптов** (CD для промптов).
3. **CI eval-gate / regression testing для LLM** — регрессия промпта блокирует мёрдж.
4. **Online evaluation / LLM-as-judge в проде** (не offline-бенч).
5. **LLM output drift / quality monitoring**.
6. **Cost & latency SLO / бюджеты для LLM** («LLM FinOps»).
7. **Continuous evaluation loop** — LLM-аналог continuous training.
8. **Productionized model routing + semantic caching**.

**Net-new ИНСТРУМЕНТЫ** (реально новые для портфолио): **promptfoo**, **MLflow Prompt Registry**, **Arize Phoenix**.

**Что НЕ добавится — не дублировать в резюме (честность против раздувания):**
- MLflow (база), Prefect, DVC, FastAPI, Docker Compose, GitHub Actions CI, uv/ruff/pytest — уже **sentiment-mlops**.
- Eval *вообще* (Ragas/DeepEval), RAG, Langfuse-трейсинг, MCP — уже **policywise**.
- Guardrails *как идея* (anti-injection), tier-routing *как идея*, кассеты, **LiteLLM**, **MLX** — уже **policywise/dossier**.

→ Поэтому новое держим строго в **lifecycle-автоматизации** (registry / gate / promotion / monitoring), **а не в eval** — иначе строчка дублирует policywise. LiteLLM/MLX/кассеты тут — переиспользуемый **каркас**, не герой.

**Резюме-строки, к которым идём (формулировки фиксируем сейчас, чтобы не уплыли):**
- *«Built an LLMOps control plane: prompt registry with champion/challenger promotion, CI eval-gates (promptfoo) over a versioned golden set, and an automated continuous-evaluation loop.»*
- *«Operated LLMs in production via a LiteLLM-SDK access layer with cost/latency SLOs, semantic caching, and online LLM-as-judge drift monitoring (Arize Phoenix).»* — *(не «gateway»: Proxy запрещён правилом 5)*.
- Стек-строка: `LLMOps · LiteLLM · promptfoo · MLflow Prompt Registry · Arize Phoenix · prompt versioning · LLM eval-gates · continuous evaluation`

---

## Главные правила

1. **Existence-gate, не accuracy-gate.** Итерация готова, когда инструмент *работает и виден* **И** соответствующий пункт красной нити стал демонстрируемым: промпт-версия в реестре с alias; promptfoo реально валит CI при регрессии; access-layer логирует tier+cost; Phoenix рисует дрейф; swap champion → hot-reload. **Качество триажа — НЕ ворота.** Сознательный срез помечай `# dl-lite: <потолок> → <апгрейд>`.

   **Красная линия (что gate НЕ разрешает резать).** Корректность демонстрируемого инструмента; направление зависимостей/boundary (правило 6); утечка секретов; **дисциплина LiteLLM (правило 5)**; **сам факт продвижения красной нити**.

2. **Один новый инструмент на итерацию.** Перенос каркаса из sentiment-mlops (MLflow/Prefect/DVC/Compose/Settings/тесты) и из policywise/dossier (tier-router, кассеты, LiteLLM SDK) — **не** «новый инструмент». Реально новые за проект: **promptfoo, MLflow Prompt Registry, Arize Phoenix** — по одному на итерацию.

3. **Домен — фикстура.** Один вымышленный SaaS (рабочее имя **Driftwood**, таск-трекер). Синтетические support-тикеты + размеченный **golden-сет (~40 тикетов)**. LLM-задача: тикет → `{category, priority, sentiment, needs_human, draft_reply}`. **English product, Russian docs** (язык-конвенция). **Ширину заморозить:** один продукт, **без новых выходных полей** сверх перечисленных (масштаб — числом тикетов, не полями).

   **Дизайн-контракт фикстуры:** golden-сет несёт «джокеры» — тикеты, где наивный промпт ошибается (двусмысленная категория, скрытый negative под вежливой формой), чтобы **champion/challenger-гейт имел что различать**. **Дрейф** моделируем второй пачкой тикетов («релиз продукта» → появляется новая категория) — чтобы мониторингу было что поймать.

4. **Cost-дисциплина (cloud-only; кассеты — аналог money-gate policywise).** Default LLM = OpenAI через **тиры** в `llm-tiers.yaml`. Кассеты `replay` = **$0** и дефолт, **никогда не бьют в сеть**. `live` = деньги → **спросить перед прогоном с оценкой** (весь проект ≈ $1–5). **Снапшоты моделей пиннить** (облако молча дрейфует — иронично вредно для проекта *про* дрейф; пиннинг даёт воспроизводимость). Локалка (MLX) — **опциональный хвост**, не обязательный путь.

   **Тиры заложены сразу (переключение — рантайм-флаг, не правка кода):**
   - `cheap` → `gpt-4.1-nano-<snapshot>` — **champion по умолчанию** (самая дешёвая, $0.10/$0.40 за 1M).
   - `mid` → `gpt-4o-mini-<snapshot>` — лёгкий шаг вверх, если nano не устроит.
   - `smart` → сильная (`gpt-5`/`gpt-4.1`) — **challenger** и **LLM-as-judge**.

   Роли резолвятся в тиры через `Settings` (`TRIAGE_TIER`, `JUDGE_TIER`): сменить nano→mid = одна строка env. Слои зовут `route("tier", ...)` и про модель не знают.

5. **Дисциплина LiteLLM (security — повтор policywise, красная линия).** LiteLLM **только SDK, НИКОГДА Proxy** (Proxy = поверхность CVE). Один **голый** `acompletion`, **без callbacks/success_callback** (каждый — канал утечки). **Телеметрия off.** Ленивый импорт, **пиннинг версии + uv.lock**. base_url/ключи **только через `Settings`**. Цель — «чтобы никто ничего не украл с компьютера»: blast radius = один исходящий вызов, который мы контролируем.

6. **Слои `app/`.** Транспорты (`cli`/`ui`) — тонкие адаптеры. Workflow (оркестрация жизненного цикла: eval-прогон, gate, промоушен) — не знает про драйвер реестра. Domain — чистые функции + схемы (парсинг триажа, решение gate), без I/O. Persistence — MLflow/реестр-репозитории. `llm/` — поперечное (router/кассеты/access-layer).

   **Швы (фиксируем один раз):** `domain/` не импортирует `app/*`; поток строго внутрь `transport → workflow → domain/persistence`; вызовы между слоями — обычные функции, зависимости аргументами (без DI-фреймворка); реестр-хендл открывается на boundary и передаётся вниз; env — только через `Settings`.

7. **Eval — не герой.** policywise уже отработал DeepEval/Ragas. promptfoo здесь — **инструмент гейта**, не исследовательский вклад. DeepEval/Ragas/собственные метрики **не тащим**.

8. **Verify the store, not the UI.** После промоушена — запрос к самому MLflow-реестру (alias `champion` указывает на версию N), не верь UI.

9. **`jq` вместо `python3 -c`** для разбора JSON в shell.

10. **Коммиты:** автор — пользователь. Никогда не добавляй `Co-Authored-By: Claude`.

## Цикл итерации

`/iterationStart N` (спека → реализация → ревью-пайплайн → `/simplify`) → `/iterationClose N` (церемония без правок кода: `make check` → доки → ROADMAP → стейдж + предложенный commit-месседж) → пользователь коммитит. Каждая спека итерации **называет пункт красной нити**, который двигает.

## Что осознанно НЕ делаем

fine-tuning / LoRA (отдельная территория — train-инфра, как Temporal в dossier) · vector-RAG (policywise) · мульти-агент (dossier) · **LiteLLM Proxy/gateway** (правило 5) · prod-deploy / k8s / автоскейл · новые выходные поля в триаже · eval-фреймворк как исследовательский вклад · локалку как обязательный путь (опц. хвост) · собственные метрики качества (existence-gate, не accuracy).

## Стек: развилки уже решены

OpenAI (cloud LLM, тиры) · **LiteLLM SDK** (доступ, SDK-only — каркас policywise) · **MLflow Prompt Registry** (реестр промптов + champion/challenger — новый) · **promptfoo** (CI eval-gate — новый) · **Arize Phoenix** (online observability + drift — новый; Evidently-LLM — отклонённая альтернатива) · перенос из sentiment-mlops: Prefect (расписание промоушена), DVC (версия golden-сета), Compose, Settings · кассеты (record/replay). Полный разбор появится в `docs/tech-decisions.md`. **Не пересматривать без явного решения.**
