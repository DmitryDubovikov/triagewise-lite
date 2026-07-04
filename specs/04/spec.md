# Итерация 04 — semantic cache поверх access-layer

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель

Надстроить над access-layer (iter 3) **semantic cache**: повтор или близкий по смыслу
запрос отдаётся из кэша **без сетевого вызова** (и без кассеты), промах идёт обычным
`route()`-путём. Hit/miss виден в SLO-логе, hit-rate считается по нему.

## 🧵 Красная нить (резюме)

> **Productionized routing + semantic caching** — semantic cache поверх готового
> access-layer (iter 3): повтор/близкий запрос → **hit** без сетевого вызова; метрика
> hit-rate; промах → нормальный `route`-путь (кассеты `replay`-нейтральны).

## Новые инструменты (и минимальный объём каждого)

- Резюме-инструмента нет (итерация — надстройка, правило 2 не тратится).
- **fastembed** *(машинерия, dep в uv-env — не «новый инструмент» и не клаттер)*:
  локальные ONNX-эмбеддинги, $0/вызов, офлайн после одноразовой загрузки модели
  (~30 МБ, не LLM-деньги). Egress не расширяется: blast radius остаётся
  один `acompletion` (правило 5).

## Решённые развилки (обсуждено)

- Близость — **локальные эмбеддинги fastembed** (решение пользователя; OpenAI
  embeddings = второй egress + деньги, lexical = нечестный «semantic»).
- Кэш **выключен по умолчанию** (`SEMANTIC_CACHE_ENABLED=1` включает) — рантайм-флаг
  как у тиров; дефолтный replay-путь и CI не меняются вообще.
- Стор — **JSONL-файл** (`logs/semantic_cache.jsonl`, путь в `Settings`; append-only,
  как SLO-лог), линейный скан косинусов.
  `# dl-lite: linear-scan JSONL → vector store (FAISS/qdrant)`.
- Скоуп совпадения: эмбеддится **контент последнего user-сообщения**; неймспейс =
  `sha256(model + messages[:-1])` — смена тира или промпт-версии никогда не отдаёт
  чужой ответ. Порог — `Settings` (`SEMANTIC_CACHE_THRESHOLD`, дефолт 0.90).
- Эмбеддер — **зависимость аргументом** (`route(..., embedder=...)`); дефолт — ленивый
  fastembed (как litellm: replay-тесты его не импортируют). Тесты — фейковый эмбеддер.

## Done-gate (по факту существования)

1. В `replay` + кэш включён: триаж DW-001 → `cache:"miss"` (кассета), повтор →
   `cache:"hit"`; тикет-парафраз DW-011 (без кассеты!) → `cache:"hit"` — близкий
   запрос обслужен без сети и без кассеты.
2. SLO-лог несёт поле `cache: hit|miss|off`; `make cache-stats` (jq, правило 9)
   печатает hit-rate.
3. Кэш выключен (дефолт) → поведение iter 3 байт-в-байт: `cache:"off"`, стор не
   создаётся; `import app.llm.router` не тянет `fastembed` (ленивость, тест).
4. Ревью-пайплайн чист (CRITICAL/BUG = 0).

Идемпотентность: hit не дописывает стор → повторные прогоны сходятся к стабильному
состоянию (1 запись на уникальный запрос), лог append-only (заявлено в iter 3).

## Шаги

1. `app/llm/semcache.py`: косинус + lookup/append по JSONL-стору за швом
   `open_session()` (route только секвенирует hit/miss/off),
   `default_embedder()` с ленивым fastembed.
2. `Settings`: `semantic_cache_enabled/threshold/path/embed_model`; `pyproject`:
   `fastembed` (пин в `uv.lock`).
3. `router.py`: lookup до диспатча режимов (hit → ответ + SLO-запись, минуя
   кассету/сеть), miss → обычный путь + store; поле `cache` в `CallRecord`.
4. Фикстура DW-011 (парафраз DW-001) + `make cache-stats` (jq по SLO-логу).
5. Тесты в `replay` с фейковым эмбеддером: repeat-hit, paraphrase-hit без кассеты,
   below-threshold-miss, cache-off неизменность, ленивость импорта. Затем
   ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope

Phoenix/online-judge (iter 5) · continuous-eval петля (iter 6) · vector store/ANN ·
кэш для promptfoo/внешних харнессов (владеют своими вызовами) · TTL/eviction-политики ·
изменение сигнатуры `route() -> str` · новые поля триажа · redis/сервисы (файл, не демон).
