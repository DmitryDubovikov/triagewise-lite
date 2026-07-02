# Итерация 01 — MLflow Prompt Registry

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.
> Новый инструмент один — **MLflow Prompt Registry**: промпт триажа переезжает из кода в реестр
> как версионируемый артефакт с алиасами `champion`/`challenger`.

## Зачем это (продукт и ценность)

triagewise-lite сортирует входящие support-тикеты вымышленного SaaS *Driftwood* (таск-трекер):
по каждому тикету модель определяет категорию, приоритет, тон, решает, нужен ли живой человек, и
набрасывает черновик ответа. Но продукт здесь — не сам сортировщик, а **операционный контроль над
LLM-конвейером**, который эту сортировку делает.

Ценность достаётся саппорт-лиду и ops-инженеру: вместо «однажды подобрали удачный промпт, вставили
его в код и молимся, что никто не сломает» команда получает промпт как **управляемый артефакт** — с
растущей историей версий и возможностью откатиться или продвинуть кандидата. Именно это прибавила
текущая итерация: текст промпта больше не зашит в исходниках, а живёт в реестре. Каждая правка промпта
добавляет туда новую версию (`v1, v2, v3, …` — без потолка), а поверх версий висят две подвижные
метки-роли: `champion` — та версия, что сейчас работает в проде, и `challenger` — претендент, которого
позже будут проверять против чемпиона. Метки не плодят версий, они лишь указывают, какая версия какую
роль играет сейчас; при промоушене (iter 6) метка `champion` просто переезжает на выигравшую версию.
Это первый кирпич CD-для-промптов: появилось *куда* промоутить (iter 6) и *что* гонять через eval-gate
(iter 2).

## 🧵 Что это дало резюме

Делает демонстрируемой north-star строку **«Prompt-as-artifact + champion/challenger промоушен
промптов»** (ROADMAP, строка 1). Доказательство-артефакт: промпт `triage` лежит в MLflow Prompt
Registry как версия (v1, v2), алиасы `champion`→v1 и `challenger`→v2 проставлены и подтверждаются
**запросом к самому реестру** (`get_prompt_version_by_alias` и REST `…/registered-models/alias`),
а боевой триаж-поток грузит промпт **по алиасу**, а не из хардкода. Сам swap алиаса (промоушен)
отложен в iter 6 — здесь демонстрируется prompt-as-artifact и факт существования двух кандидатов.

## TL;DR (простыми словами)

Было — промпт триажа жил константой `_SYSTEM` прямо в коде workflow. Стало — тот же текст
зарегистрирован в MLflow Prompt Registry как версия с алиасом `champion`, рядом заведён вариант-
претендент под алиасом `challenger`, а триаж теперь **загружает промпт из реестра по алиасу** перед
вызовом модели. Champion-шаблон при этом байт-в-байт повторяет старый промпт, поэтому записанная
кассета осталась валидной и смок по-прежнему гоняется офлайн за $0. Главное, что добавилось: промпт
стал версионируемым артефактом control-plane, а не строкой в исходнике.

## Что это за инструмент

**MLflow Prompt Registry** — это реестр промптов: хранилище, где текст промпта живёт как
версионируемый артефакт, примерно как код в git. Сам MLflow уже знаком по sentiment-mlops (там его
registry хранил версии моделей) — Prompt Registry это та же машинерия, но для промптов. Нужен он
здесь, чтобы вынуть промпт из исходников и дать ему то, чего у строки в коде нет: историю версий,
именованные роли и возможность откатиться или продвинуть кандидата.

Три понятия, которыми дальше оперирует весь документ:
- **версия** — неизменяемый снимок текста промпта под номером (`v1, v2, v3, …`); каждая правка промпта
  добавляет новую версию, а старые остаются на месте.
- **alias** — подвижная метка-роль (у нас `champion` и `challenger`), которая указывает на одну из
  версий. Метка не создаёт версий — она лишь говорит, какая версия сейчас играет роль; при промоушене
  (iter 6) метка переезжает на другую версию.
- **шаблон (chat template)** — сам промпт в виде списка сообщений `{role, content}` с пропусками
  `{{subject}}` и `{{body}}`, которые подставляются текстом тикета прямо перед вызовом модели.

## Поток данных

Само по себе здесь ничего не запускается — всё начинает человек. Оператор саппорта хочет разобрать
конкретный тикет, например DW-001, и набирает в терминале одну команду:

```
uv run python -m app.cli.main DW-001
```

Эта команда — причина всей цепочки ниже. Дальше — по шагам, что она приводит в движение.

**Программе нужно вернуть оператору разобранный тикет, а чтобы его разобрать, нужен промпт** — текст-
инструкция, по которой модель классифицирует тикет. С этой итерации промпт больше не лежит в коде: он
хранится в реестре MLflow. Поэтому самый первый шаг — подключиться к реестру, иначе модель нечем
инструктировать. Подключается тонкий входной слой программы (`app/cli/main.py`, то, что стартует от
набранной команды): он открывает соединение один раз и отдаёт его дальше — в слой-оркестратор
(`workflow`), — а сам промпт не читает. Так вся работа с реестром живёт на входе в программу, а не
растекается по остальным слоям (этого требует правило 6).

**Оркестратор достаёт из реестра нужную версию промпта.** Он спрашивает у реестра: на какую версию
сейчас указывает алиас `champion` (алиас — это подвижная метка на конкретную версию)? — и получает
её. В промпте оставлены два пропуска, `{{subject}}` и `{{body}}`; оркестратор вставляет в них тему и
текст тикета DW-001 — так получается готовый набор сообщений для модели.

**Эти сообщения уходят в `route()` — единственную дверь к модели.** С iter 0 она не изменилась: по
умолчанию (`replay`) `route()` не звонит в сеть, а берёт заранее записанный ответ из файла-кассеты на
диске. Ответ поднимается обратно, программа разбирает его в структуру `TriageResult` и печатает
оператору в терминал.

Против iter 0 изменилось ровно одно звено: **откуда взялся промпт**. Раньше — константа прямо в коде,
теперь — версия, загруженная из реестра по алиасу. Всё остальное на пути к модели осталось прежним.

```
            LLM_MODE=replay (default, $0)         MLflow Prompt Registry (Docker, :5050)
                        │                                      │
  tickets.jsonl ──load──► CLI ──open_registry(settings)──► MlflowClient ──┐
   (фикстура)             │                                      │         │
                          │   triage_ticket(ticket, tier, client=…, alias="champion")
                          │                                      │         │
                          │     load_triage_prompt(client, "champion") ◄───┘  prompts:/triage@champion
                          │                          │
                          │     format_for_ticket(prompt, ticket) ──► messages
                          │                          │
                          │                   route("cheap", messages)
                          │                          │
                          │                   cassettes/<key>.json ──► content   (сеть НЕ трогается)
                          ▼                          │
                    печать TriageResult ◄── parse_triage(content)

  Заливка промпта в реестр (НЕ LLM, денег не стоит):
       scripts/register_prompt.py ──► sync_prompts(client) ──► (register_prompt + set_prompt_alias, только если шаблон изменился)
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `open_registry(settings)` (persistence) | открывает клиент `MlflowClient` на boundary из `Settings.mlflow_tracking_uri` | возвращает клиент |
| `sync_prompts(client)` (persistence) | приводит реестр к шаблонам champion/challenger из кода; новую версию создаёт только при изменении (идемпотентно) | в MLflow-реестр (`prompts:/triage`) |
| `load_triage_prompt(client, alias)` (persistence) | грузит версию промпта, на которую указывает алиас | возвращает `PromptVersion` |
| `format_for_ticket(prompt, ticket)` (persistence) | рендерит чат-шаблон `{{subject}}/{{body}}` в сообщения | возвращает `list[dict]` |
| `route("tier", messages)` (llm, без изменений) | единый chokepoint; в `replay` читает кассету | возвращает текст ответа |
| `parse_triage` (domain) | разбирает JSON в `TriageResult` | возвращает Pydantic-модель |

Чего в этой итерации **НЕ** происходит (типичная путаница): **нет промоушена/swap** — алиас
`champion` никуда не «переезжает» (это iter 6); challenger заведён, но через него никто не гоняет в
смоке (его существование проверяется запросом к стору, не прогоном). Нет eval-gate (iter 2), нет
cost/latency-лога (iter 3), нет дрейфа (iter 5). Промпт **не улучшался** — champion перенесён из
iter 0 как есть (existence-gate, не accuracy).

## Слои и направление зависимостей (правило 6, «опция A»)

Развилку «кто грузит промпт» решили в пользу **опции A**: хендл реестра открывается на транспортном
boundary и течёт вниз аргументом; workflow грузит промпт и форматирует его; а `route()` остаётся
**нетронутым** message-based chokepoint'ом и реестр не импортирует. Весь MLflow-prompt-API заперт в
одном модуле `persistence/prompts.py` — `domain/` и `llm/` про MLflow не знают.

```
  cli/main.py ──open_registry──► persistence/prompts.py  (MlflowClient + prompt-API живут ТОЛЬКО здесь)
       │                              ▲
       │  client=…                    │ load_triage_prompt / format_for_ticket
       ▼                              │
  workflow/triage_flow.py ────────────┘
       │
       └──► llm/router.py  (route(): tier→model→cassette; реестр НЕ импортирует — шов сохранён)
                  │
            domain/triage.py  (чистый: схема + парсинг; ни app/*, ни mlflow)
```

## Карта «где в коде»

> Номера строк — ориентир на момент итерации 1; опирайся на имена символов, они переживают дрейф строк.

1. **Реестр-репозиторий (единственный дом MLflow-prompt-API)** — `app/persistence/prompts.py`.
   Это новый модуль, в котором живёт вся работа с реестром промптов: константы имени и алиасов,
   чат-шаблоны-сиды, открытие хендла, сидирование и загрузка по алиасу. Импорт `mlflow` ленивый
   (внутри `open_registry`), по образцу ленивого `import litellm` из iter 0 — модули, которым реестр
   не нужен, тяжёлый SDK не тянут.
   ```python
   TRIAGE_PROMPT_NAME = "triage"
   CHAMPION = "champion"
   CHALLENGER = "challenger"

   def open_registry(settings: Settings | None = None) -> MlflowClient:
       from mlflow import MlflowClient  # лениво
       settings = settings or get_settings()
       uri = settings.mlflow_tracking_uri
       return MlflowClient(tracking_uri=uri, registry_uri=uri)
   ```

2. **Заливка champion + challenger в реестр, идемпотентно (единый источник истины)** —
   `app/persistence/prompts.py`, `sync_prompts()`. Функция приводит реестр в соответствие с
   шаблонами из кода: для каждой метки смотрит, что на неё сейчас указывает, и **регистрирует новую
   версию только если шаблон реально изменился** — иначе оставляет версию как есть и просто
   подтверждает метку. Поэтому повторный запуск не плодит одинаковые версии. Её зовут все трое
   потребителей — демо-скрипт, офлайн-автор кассеты и тестовая фикстура, — поэтому зарегистрированный
   промпт, который определяет ключ кассеты, не может разъехаться между ними. Текущую версию под меткой
   она читает **прямо из стора** (`get_prompt_version_by_alias`), а не через кэширующий `load_prompt`:
   кэш последнего ключуется только по URI промпта и «протёк» бы между разными реестрами в одном
   процессе (например, в тестах).
   ```python
   class SyncedPrompt(NamedTuple):
       version: int
       created: bool   # True — зарегистрирована новая версия; False — совпала с существующей

   def sync_prompts(client: MlflowClient) -> dict[str, SyncedPrompt]:
       desired = ((CHAMPION, TRIAGE_CHAMPION_TEMPLATE), (CHALLENGER, TRIAGE_CHALLENGER_TEMPLATE))
       synced = {}
       for alias, template in desired:
           current = _current_version(client, alias)          # get_prompt_version_by_alias, не кэш
           if current is not None and current.template == template:
               synced[alias] = SyncedPrompt(current.version, created=False)
               continue
           pv = client.register_prompt(name=TRIAGE_PROMPT_NAME, template=template,
                                       commit_message=f"sync {alias}")
           client.set_prompt_alias(TRIAGE_PROMPT_NAME, alias, pv.version)
           synced[alias] = SyncedPrompt(pv.version, created=True)
       return synced
   ```

3. **Загрузка по алиасу + рендер в сообщения** — `app/persistence/prompts.py`, `load_triage_prompt()`
   и `format_for_ticket()`. Первая грузит версию промпта по URI `prompts:/triage@<alias>` (verify в
   сторе, не UI — правило 8). Вторая — единственное место, где чат-шаблон с плейсхолдерами
   `{{subject}}/{{body}}` форматируется тикетом в список сообщений; общий дом нужен, чтобы боевой
   поток и офлайн-автор кассеты рендерили одинаково и ключ кассеты не дрейфовал.
   ```python
   def load_triage_prompt(client: MlflowClient, alias: str) -> PromptVersion:
       return client.load_prompt(f"prompts:/{TRIAGE_PROMPT_NAME}@{alias}")

   def format_for_ticket(prompt: PromptVersion, ticket: Ticket) -> list[dict[str, Any]]:
       return cast("list[dict[str, Any]]", prompt.format(subject=ticket.subject, body=ticket.body))
   ```

4. **Триаж-поток грузит промпт по алиасу** — `app/workflow/triage_flow.py`, `triage_ticket()`.
   Раньше функция строила сообщения из зашитой константы `_SYSTEM`; теперь она принимает хендл
   реестра аргументом, грузит промпт по алиасу (`champion` по умолчанию), форматирует его тикетом и
   зовёт `route()`. `route()` при этом не изменился — поток остаётся `load → format → route → parse`.
   ```python
   async def triage_ticket(ticket, *, tier, client, alias=CHAMPION, settings=None):
       prompt = load_triage_prompt(client, alias)
       messages = format_for_ticket(prompt, ticket)
       content = await route(tier, messages, settings=settings)
       return parse_triage(content)
   ```

5. **CLI открывает хендл на boundary** — `app/cli/main.py`, `main()`. Тонкий транспорт теперь, помимо
   чтения фикстуры, открывает `MlflowClient` через `open_registry(settings)` и передаёт его в
   workflow. Так реестр-хендл рождается на границе и течёт вниз — шов «опции A».
   ```python
   client = open_registry(settings)
   result = asyncio.run(
       triage_ticket(ticket, tier=settings.triage_tier, client=client, settings=settings)
   )
   ```

6. **Демо-скрипты: залить и посмотреть промпт** — `scripts/register_prompt.py` и
   `scripts/show_prompt.py`. Первый заливает промпт в боевой реестр (docker-MLflow) через тот же
   `sync_prompts()` и печатает подробный итог: куда залил, какая версия под каждой меткой и создалась
   ли новая версия (`registered new version`) или всё уже актуально (`unchanged, alias confirmed`).
   Второй отвечает на вопрос «а что за текст лежит в реестре?» — вытаскивает шаблон под меткой и
   печатает его. Оба обращаются только к реестру — **никакого LLM-вызова, денег не стоит**.
   ```python
   # register_prompt.py
   synced = sync_prompts(client)
   for alias, result in synced.items():
       state = "registered new version" if result.created else "unchanged, alias confirmed"
       print(f"  prompts:/{TRIAGE_PROMPT_NAME}@{alias} -> v{result.version}  ({state})")

   # show_prompt.py — read-only просмотр артефакта
   prompt = load_triage_prompt(open_registry(), alias)
   print(json.dumps(prompt.template, indent=2, ensure_ascii=False))
   ```

7. **Офлайн-автор кассеты переведён на реальный путь рендера** — `scripts/author_cassette.py`,
   `main()`. Чтобы ключ кассеты гарантированно совпадал с боевым потоком, скрипт поднимает
   **throwaway sqlite-реестр** во временной папке, заливает в него промпт тем же `sync_prompts()`,
   грузит champion и форматирует тикет тем же `format_for_ticket()` — а не реконструирует сообщения
   вручную. Всё офлайн, без сети, $0. Реальный sqlite-uri он получает, подменив только поле реестра в
   `Settings` через `model_copy`, сохранив боевые пути.
   ```python
   with tempfile.TemporaryDirectory() as tmp:
       offline = settings.model_copy(update={"mlflow_tracking_uri": f"sqlite:///{Path(tmp) / 'reg.db'}"})
       client = open_registry(offline)
       sync_prompts(client)
       prompt = load_triage_prompt(client, CHAMPION)
       messages = format_for_ticket(prompt, ticket)
   ```

8. **Полный `mlflow` в зависимостях + офлайн-тесты** — `pyproject.toml` и `tests/test_route_replay.py`.
   В зависимости добавлен **полный** `mlflow` (не skinny): skinny не несёт sqlite-registry-store, а он
   нужен, чтобы тесты гоняли реестр офлайн без сервера. Фикстура `registry` поднимает sqlite-реестр во
   временной папке, заливает промпт и отдаёт клиент; тесты проверяют happy-path в `replay`, факт, что
   оба алиаса резолвятся в разные версии (verify в сторе), и идемпотентность повторного `sync_prompts()`
   (новых версий не создаётся). mypy-override для `mlflow.*` локализован в `pyproject.toml` (у mlflow
   нет годных стабов).
   ```python
   @pytest.fixture
   def registry(tmp_path):
       settings = Settings(llm_mode="replay", mlflow_tracking_uri=f"sqlite:///{tmp_path / 'reg.db'}")
       client = open_registry(settings)
       synced = sync_prompts(client)
       versions = {alias: s.version for alias, s in synced.items()}
       return client, settings, versions
   ```
