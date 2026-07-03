# Итерация 03 — LiteLLM access-layer: cost/latency SLO

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.
> Нового инструмента в этот раз нет — углубляем уже перенесённый из policywise **LiteLLM SDK**
> до полноценного access-layer: каждый LLM-вызов получает цену и время, пишется в SLO-лог,
> а дисциплина безопасности (правило 5) превращается из докстринга в падающий тест.

## Зачем это (продукт и ценность)

triagewise-lite сортирует входящие support-тикеты вымышленного SaaS *Driftwood*: по каждому тикету
модель определяет категорию, приоритет, тон, решает, нужен ли живой человек, и набрасывает черновик
ответа. Продукт при этом — не сам сортировщик, а операционный контроль над LLM-конвейером.

До этой итерации конвейер тратил деньги вслепую: вызов уходил в OpenAI, ответ возвращался, а сколько
стоил этот тикет и не деградировала ли скорость — никто не записывал. Для саппорт-лида это две
реальные боли: счёт от провайдера приходит одной непрозрачной суммой в конце месяца, и нет способа
заметить, что «подешевле» модель на потоке тикетов вдруг стала отвечать по десять секунд. Теперь у
каждого разобранного тикета есть ценник и секундомер: access-layer записывает цену и длительность
каждого вызова в журнал, а заданные бюджеты (максимум долларов и миллисекунд на вызов) громко
предупреждают о превышении. Плюс переключение всего конвейера между дешёвой и умной моделью — одна
переменная окружения, без правки кода: можно сравнить цену одного и того же тикета на двух тирах
по журналу.

## 🧵 Что это дало резюме

Делает демонстрируемой north-star строку **«Cost & latency SLO / бюджеты для LLM (LLM FinOps)» плюс
половину «productionized routing»** (ROADMAP, строка 3). Доказательства-артефакты: журнал
`logs/llm_calls.jsonl`, где у каждого вызова записаны тир, модель, режим, латентность, цена в
долларах и список нарушенных бюджетов; кассеты с реальными записанными ценами (nano-вызов стоил
$0.0000377, gpt-4.1 — $0.000962); и security-гейт `tests/test_litellm_discipline.py`, который
механически доказывает дисциплину LiteLLM из правила 5 — «SDK-only, без Proxy, без callbacks» теперь
не обещание в доке, а тест, падающий при нарушении.

## TL;DR (простыми словами)

Было — `route()` дёргал модель и возвращал текст, больше ничего: ни цены, ни времени, ни следа.
Стало — каждый вызов оставляет строку в журнале: какой тир, какая модель, какой режим, сколько
миллисекунд, сколько долларов и уложился ли в бюджет. Цену на живом вызове считает
`litellm.completion_cost` и она же записывается в кассету — поэтому офлайн-реплей бесплатен, но
показывает настоящую цену записанного вызова. Бюджеты задаются двумя переменными окружения;
превышение — предупреждение в лог, вызов не валится. И отдельно: пять правил обращения с LiteLLM
теперь проверяет pytest, а не память ревьюера.

## Что это за инструмент

Нового инструмента нет, но два понятия, которыми оперирует документ, стоит развернуть.

**`litellm.completion_cost`** — функция из LiteLLM SDK, которая по ответу модели считает цену вызова
в долларах: у LiteLLM внутри зашита таблица прайсингов (модель → цена за 1M входных/выходных
токенов), и она умножает её на фактический расход токенов из поля `usage` ответа. То есть цену не
нужно считать руками и хардкодить тарифы — SDK, через который вызов и шёл, сам знает, почём он был.

**SLO** (service-level objective) — целевой порог качества сервиса, выраженный числом; у нас их два
на каждый вызов: максимум долларов (`SLO_MAX_COST_USD`, дефолт $0.05) и максимум миллисекунд
(`SLO_MAX_LATENCY_MS`, дефолт 15 000). Нарушение порога называется *breach*: оно попадает в журнал
и в WARNING, но вызов не прерывает — это наблюдаемость, а не рубильник (сознательное решение,
см. `learnings.md`).

## Поток данных

Оператор разбирает тикет как и раньше: `uv run python -m app.cli.main DW-001`. Снаружи ничего не
изменилось — тот же JSON триажа на stdout. Изменилось то, что происходит вокруг LLM-вызова внутри
`route()`: теперь это не «дёрнуть и вернуть», а «замерить, дёрнуть, оценить цену, свериться с
бюджетом, записать след».

```
оператор: uv run python -m app.cli.main DW-001         (TRIAGE_TIER решает: cheap или smart)
    │
    ▼
route(tier, messages)                    app/llm/router.py
    │  тир → модель (llm-tiers.yaml), старт секундомера
    │
    ├─ LLM_MODE=replay (дефолт, $0) ──► кассета cassettes/<sha256>.json
    │                                     content ── ответ модели
    │                                     cost_usd ─ цена, записанная при record
    │
    └─ LLM_MODE=record|live (деньги) ─► litellm.acompletion ──► OpenAI
                                          цена = litellm.completion_cost(ответ)
                                          record: content+usage+cost_usd → кассета
    │
    ▼
slo.log_call(...)                        app/llm/slo.py
    │  check_slo: цена/латентность против бюджетов из Settings
    │
    ├──► logs/llm_calls.jsonl            (append, одна JSON-строка на вызов)
    └──► stderr                          [slo] cheap->gpt-4.1-nano… 0ms $0.000038 (cassette) ok
```

| Инструмент | Что делает | Куда пишет |
|---|---|---|
| `route()` (`app/llm/router.py`) | резолвит тир в модель, меряет латентность, добывает цену (живую или из кассеты) | ничего сам — передаёт всё в `slo.log_call` |
| `litellm.completion_cost` | считает цену живого вызова по usage-токенам и своей таблице прайсингов | никуда — возвращает float, роутер кладёт его в кассету |
| `slo.log_call` (`app/llm/slo.py`) | собирает запись вызова, сверяет с бюджетами (`check_slo`), пишет след | `logs/llm_calls.jsonl` + строка в stderr |
| `tests/test_litellm_discipline.py` | механически проверяет дисциплину правила 5 по исходникам, sys.modules и lock-файлу | никуда — это pytest-гейт |

Честные оговорки — чего в этой итерации **нет**. Никакой агрегации: журнал — это строки по вызовам,
«сколько потратили за день/прогон» никто не суммирует (это сырьё для Phoenix в iter 5). Никакого
enforcement: breach предупреждает, но не блокирует и не переключает тир. И `latency_ms` в
replay-строке — это время чтения кассеты с диска (доли миллисекунды), а не сетевой раунд-трип;
отличить одно от другого позволяет поле `mode` в той же строке.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; имена символов надёжнее.

1. **SLO-модуль — `app/llm/slo.py` (`CallRecord:26`, `check_slo:37`, `log_call:47`).**
   Весь учёт вызовов живёт в одном новом модуле из трёх частей. `CallRecord` — pydantic-схема одной
   строки журнала. `check_slo()` — чистая функция без I/O: получает цену, латентность и настройки,
   возвращает список нарушенных бюджетов (пустой = всё в норме). `log_call()` собирает запись,
   дописывает её строкой в JSONL-журнал и зеркалит человекочитаемую строку в логгер — WARNING при
   breach, INFO иначе.

   ```python
   def check_slo(cost_usd: float, latency_ms: float, settings: Settings) -> list[str]:
       """Pure decision: which per-call SLO thresholds does this call breach?"""
       breaches = []
       if cost_usd > settings.slo_max_cost_usd:
           breaches.append(f"cost ${cost_usd:.6f} > ${settings.slo_max_cost_usd:.6f}")
       if latency_ms > settings.slo_max_latency_ms:
           breaches.append(f"latency {latency_ms:.0f}ms > {settings.slo_max_latency_ms:.0f}ms")
       return breaches
   ```

2. **Роутер стал access-layer — `app/llm/router.py` (`route:26`).** Сигнатура не изменилась
   (`route(tier, messages) -> str` — слои выше ничего не заметили), но вокруг обоих путей появился
   секундомер и добыча цены. В replay цена читается из кассеты, если та её несёт
   (`cost_source="cassette"`); рукописные кассеты без цены дают честные `0.0` и `"none"`.
   В record/live цену считает `completion_cost`, и record тут же кладёт её в кассету — чтобы все
   последующие реплеи показывали реальный ценник за $0.

   ```python
   if settings.llm_mode == "replay":
       response = cassettes.load(settings.cassettes_dir, key)
       # ...
       if "cost_usd" in response:  # what the recorded call cost; actual spend here is $0
           cost_usd, cost_source = float(response["cost_usd"]), "cassette"
   else:
       content, usage, live_cost = await _live_completion(model, messages, settings)
       # ... record: payload = {"content", "usage", "cost_usd"} → кассета

   latency_ms = (time.perf_counter() - start) * 1000
   slo.log_call(tier=tier, model=model, settings=settings,
                latency_ms=latency_ms, cost_usd=cost_usd, cost_source=cost_source)
   ```

3. **Живой путь возвращает цену — `app/llm/router.py` (`_live_completion:69`).** Единственный голый
   `acompletion` остался на месте, но теперь функция возвращает тройку `(content, usage, cost)`.
   Цена считается в try/except: если у LiteLLM нет прайсинга на модель, вызов не должен упасть уже
   после того, как деньги потрачены, — тогда возвращается `None`, и в кассету ключ `cost_usd`
   не пишется вовсе (а не врёт «записанный $0»).

   ```python
   usage = getattr(resp, "usage", None)
   usage_dict = usage.model_dump(exclude_none=True) if usage is not None else None
   try:
       cost = float(litellm.completion_cost(completion_response=resp))
   except Exception:
       cost = None
   return content, usage_dict, cost
   ```

4. **Бюджеты и путь журнала — `app/config.py` (`slo_max_cost_usd:34`, `llm_log_path:39`).**
   Пороги и путь к журналу заведены в `Settings` — единственный шлюз к env (правило 6). Ужать бюджет
   для демо или CI — одна переменная окружения, без правки кода.

   ```python
   slo_max_cost_usd: float = 0.05
   slo_max_latency_ms: float = 15_000
   llm_log_path: Path = _ROOT / "logs" / "llm_calls.jsonl"
   ```

5. **Security-гейт правила 5 — `tests/test_litellm_discipline.py` (пять тестов, строки 34–79).**
   Дисциплина LiteLLM теперь проверяется механически, по пяти осям: (1) в `app/` нет `litellm.proxy`
   и никаких обращений к litellm за пределами разрешённой поверхности из шести имён; (2) SDK
   импортируется ровно в одном месте — роутере, причём гейт ловит обе формы импорта
   (`import litellm` и `from litellm import …`); (3) телеметрия и все callback-каналы обнуляются
   строго до `acompletion`; (4) сабпроцесс подтверждает ленивость — `import app.llm.router` не тянет
   `litellm` в `sys.modules`, то есть replay живёт вообще без SDK; (5) версия запиннена: диапазон в
   `pyproject.toml` и точная резолвнутая версия в `uv.lock`.

   ```python
   def test_replay_never_imports_the_sdk():
       """Lazy import holds: importing the router does not pull litellm into the process."""
       code = "import sys; import app.llm.router; assert 'litellm' not in sys.modules"
       subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)
   ```

6. **Транспорт включает логирование — `app/cli/main.py:26`.** Access-layer только пишет в логгер;
   кто и куда этот логгер выводит — решает транспорт (шов правила 6: композиция на boundary).
   CLI настраивает `logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")`,
   поэтому SLO-строка видна при каждом запуске из терминала.

7. **Тесты access-layer — `tests/test_route_replay.py` (`test_slo_log_written_on_replay:79`,
   `test_check_slo_flags_cost_and_latency_breaches:94`).** Happy-path проверяет, что replay-вызов
   дописал ровно одну строку журнала с правильными полями (фикстура уводит `llm_log_path` в
   `tmp_path`, чтобы тесты не сорили в рабочий журнал), а юнит на `check_slo` — что оба бюджета
   срабатывают и оба названы в сообщении.
