# Итерация 00 — Каркас (LLMOps-скелет)

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.
> Новых инструментов нет — это перенос каркаса из соседних проектов, чтобы все швы встали на места.

## Зачем это (продукт и ценность)

triagewise-lite закрывает понятную боль саппорта: входящие support-тикеты вымышленного SaaS
*Driftwood* (таск-трекер) нужно надёжно сортировать — определить категорию, приоритет, тон,
решить, нужен ли живой человек, и набросать черновик ответа — не разбирая каждый тикет руками.
Но продукт здесь не само приложение-сортировщик, а **операционный контроль над LLM-конвейером**,
который эту сортировку делает: чтобы промпты были версионированы, регрессии ловились до релиза,
дрейф качества был виден, а лучший промпт продвигался автоматически.

Бизнес-ценность достаётся саппорт-лиду и ops-инженеру: вместо «однажды подобрали промпт и молимся»
они получают управляемый жизненный цикл LLM. Эта первая итерация сама по себе ещё ничего не
сортирует «в проде» — она закладывает фундамент, на котором всё перечисленное станет возможным:
единую точку входа к модели, детерминированный офлайн-режим без трат, запиненные версии моделей
и чистые границы между слоями.

## 🧵 Что это дало резюме

Делает демонстрируемой north-star строку **«LLMOps-скелет заложен»** (ROADMAP, строка 0). Сама по
себе резюме-практику она не закрывает, но даёт артефакт-фундамент: единый chokepoint `route("tier")`,
кассеты record/replay, тиры с механически проверяемым пиннингом снапшотов и швы слоёв — на этом
iter 1+ строят prompt-registry, eval-gate, online-eval и continuous-evaluation петлю.

## TL;DR (простыми словами)

Было — пустой репозиторий с тремя конституционными документами. Стало — рабочий скелет: одна команда
триажит тикет, по умолчанию офлайн и бесплатно (читает заранее записанный ответ-«кассету»), модель
выбирается тиром (`cheap`/`mid`/`smart`), а не хардкодом, и сменить её можно одной строкой в окружении.
Добавили две вещи, которые будут нести весь проект: единственную точку обращения к LLM (`route`) и
механизм кассет, который держит расходы на нуле и делает прогоны детерминированными.

## Поток данных

В этой итерации поток короткий: CLI берёт один тикет из фикстуры, прогоняет его через `route()` и
печатает разобранный результат. В режиме по умолчанию (`replay`) ответ берётся из закоммиченной
кассеты на диске — сеть не трогается вообще, LiteLLM-SDK даже не импортируется.

```
                    LLM_MODE=replay (default, $0, offline)
                                  │
  tickets.jsonl ──load_tickets──► CLI ──build_messages──► route("cheap", msgs)
   (фикстура)                      │                            │
                                   │                     resolve_model() ─► gpt-4.1-nano-2025-04-14
                                   │                            │
                                   │                     cassette_key(model, msgs)
                                   │                            │
                                   │                     cassettes/<key>.json ──► content
                                   │                            │
                                   ▼                     parse_triage(content)
                              печать TriageResult ◄────────────┘

  LLM_MODE=record/live (⚠️ стоит денег, гейтится явным go):
       route ─► litellm.acompletion ─► OpenAI ; record вдобавок пишет cassettes/<key>.json
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `load_tickets` (persistence) | читает синтетические тикеты из JSONL | в память (`list[Ticket]`) |
| `route("tier", msgs)` (llm) | единая точка обращения к LLM; решает replay/record/live | возвращает текст ответа |
| `resolve_model` + `llm-tiers.yaml` | резолвит тир в датированный снапшот модели | имя модели (в `cassette_key`) |
| кассеты (`cassette_key`/`load`/`save`) | детерминируют и удешевляют прогон | `cassettes/<sha256>.json` (только в `record`) |
| `parse_triage` (domain) | разбирает JSON-ответ в валидированный `TriageResult` | возвращает Pydantic-модель |

Чего в этой итерации **НЕ** происходит (типичная путаница): нет реестра промптов (промпт зашит в
коде `triage_flow.py`, версионирование — iter 1), нет eval-gate, нет cost/latency-лога, нет дрейфа и
никакого промоушена. Кассета для DW-001 — это вручную написанный *валидный по формату* ответ
(existence-gate, не accuracy); реальные кассеты появляются только через `LLM_MODE=record`.

## Слои и направление зависимостей (правило 6)

Поток строго внутрь: транспорт зовёт workflow, workflow — domain и llm; `domain/` не импортирует
ничего из `app/*`. Доступ к env — только через `Settings`.

```
  cli/main.py ──► workflow/triage_flow.py ──► domain/triage.py   (чистый: схема + парсинг)
       │                     │
       │                     └──────────────► llm/router.py ──► llm/tiers.py
       └──► persistence/tickets.py                    │           llm/cassettes.py
                                                       ▼
                                                 (litellm SDK, лениво, только record/live)
   всё, что трогает env ───────────────────────► config.py:Settings
```

## Карта «где в коде»

> Номера строк — ориентир на момент итерации 0; опирайся на имена символов, они переживают дрейф строк.

1. **Единая точка доступа к env** — `app/config.py`, класс `Settings` + `get_settings()` (строки 17-46).
   Все переменные окружения (режим кассет, тиры ролей, ключи, пути, URI реестра) читаются здесь и
   нигде больше; `get_settings()` кэширует инстанс, так что `.env` парсится один раз.
   ```python
   class Settings(BaseSettings):
       model_config = SettingsConfigDict(env_file=".env", extra="ignore")
       llm_mode: LLMMode = "replay"        # replay = $0, offline, никогда не сеть
       triage_tier: str = "cheap"
       judge_tier: str = "smart"
       openai_api_key: SecretStr | None = None
       # ... пути и mlflow_tracking_uri
   ```

2. **Единый LLM-chokepoint** — `app/llm/router.py`, функция `route()` (строки 18-38) и приватная
   `_live_completion()` (строки 41-62). `route()` резолвит тир в модель, считает ключ кассеты и в
   `replay` отдаёт сохранённый ответ, ни разу не касаясь сети; запись/живой вызов идут только в
   `record`/`live`. Сам сетевой вызов изолирован в одной голой `acompletion`, до которой в `replay`
   исполнение не доходит — поэтому LiteLLM там даже не импортируется.
   ```python
   async def route(tier, messages, *, settings=None):
       settings = settings or get_settings()
       model = resolve_model(tier, settings.tiers_path)
       key = cassettes.cassette_key(model, messages)
       if settings.llm_mode == "replay":
           response = cassettes.load(settings.cassettes_dir, key)
           if response is None:
               raise FileNotFoundError(...)   # replay никогда не уходит в сеть
           return response["content"]
       content = await _live_completion(model, messages, settings)
       if settings.llm_mode == "record":
           cassettes.save(settings.cassettes_dir, key, model, messages, {"content": content})
       return content
   ```

3. **Дисциплина LiteLLM (правило 5, красная линия)** — `app/llm/router.py`, `_live_completion()`
   (строки 41-62). Импорт `litellm` ленивый (внутри функции). Перед самым вызовом гасятся все каналы
   утечки: телеметрия выключается, списки callbacks обнуляются. Вызов — одна голая `acompletion`
   (SDK, не Proxy), ключ и base_url приходят из `Settings`.
   ```python
   import litellm  # лениво: replay никогда не импортирует SDK
   litellm.telemetry = False
   litellm.callbacks = []
   litellm.success_callback = []
   litellm.failure_callback = []
   resp = await litellm.acompletion(model=model, messages=messages, api_key=api_key, base_url=...)
   ```

4. **Pin-гейт (механически проверяемо)** — `app/llm/tiers.py`, `_SNAPSHOT_RE` + `load_tiers()`
   (строки 13, 24-30). При загрузке `llm-tiers.yaml` каждая модель проверяется на суффикс датированного
   снапшота `-YYYY-MM-DD`; плавающий алиас (типа `gpt-4.1-nano`) роняет загрузку с понятной ошибкой —
   облако иначе молча дрейфует, что иронично вредно для проекта *про* дрейф.
   ```python
   _SNAPSHOT_RE = re.compile(r"-\d{4}-\d{2}-\d{2}$")
   for tier, model in tiers.items():
       if not _SNAPSHOT_RE.search(model):
           raise ValueError(f"Tier '{tier}' -> '{model}' is not a dated snapshot ...")
   ```

5. **Кассеты record/replay** — `app/llm/cassettes.py`, `cassette_key()` / `load()` / `save()`
   (строки 18-46). Ключ — это sha256 от канонического JSON `{model, messages}`; та же функция —
   единственный источник истины и для роутера, и для офлайн-скрипта-автора, поэтому ключ не может
   разъехаться между ними. Файл на ключ хранит сам обмен в человекочитаемом виде.
   ```python
   def cassette_key(model, messages):
       canonical = json.dumps({"model": model, "messages": messages}, sort_keys=True, separators=(",", ":"))
       return hashlib.sha256(canonical.encode()).hexdigest()
   ```

6. **Замороженная схема триажа (правило 3)** — `app/domain/triage.py`, `TriageResult` + `parse_triage()`
   (строки 24-42). Выход триажа — ровно пять полей, ни одного сверх; домен чист (импортирует только
   stdlib и pydantic). `parse_triage` терпит на всякий случай ```json-обёртку, хотя промпт её запрещает.
   ```python
   class TriageResult(BaseModel):
       category: str
       priority: Priority         # low|medium|high|urgent
       sentiment: Sentiment       # negative|neutral|positive
       needs_human: bool
       draft_reply: str
   ```

7. **Тонкий транспорт** — `app/cli/main.py`, `main()` (строки 19-37). CLI — тонкий адаптер: читает
   фикстуру на boundary, выбирает тикет (по id или первый), вызывает workflow и печатает результат.
   Никакой бизнес-логики; модель не называет — только тир из `Settings`.

8. **Фикстура и офлайн-автор кассеты** — `fixtures/tickets.jsonl` (10 тикетов, среди них «джокеры»
   DW-006 «скрытый negative под вежливостью» и DW-009 «двусмысленная категория») и
   `scripts/author_cassette.py` (`main()`, строки 30-66). Скрипт строит сообщения тем же
   `build_messages`, считает тот же `cassette_key` и пишет вручную сочинённый валидный ответ — без сети,
   за $0, чтобы replay-смок был зелёным без трат.
