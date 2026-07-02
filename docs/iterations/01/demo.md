# Демо / смок — Итерация 01 (MLflow Prompt Registry)

**Что мы доказываем этим прогоном.** Итерация вынесла промпт триажа из кода в MLflow Prompt Registry:
теперь это версионируемый артефакт (версии нумеруются `v1, v2, v3, …` без потолка), а поверх версий
живут две подвижные метки-роли — `champion` (та версия, что сейчас в проде) и `challenger`
(претендент, которого проверяют против чемпиона). Боевой триаж просит у реестра версию по метке
`champion`, а не по номеру и не из хардкода — поэтому, когда метка завтра переедет на другую версию
(промоушен, iter 6), код менять не придётся. Смок проходит этот путь глазами скептика: сначала кладём промпт в реестр, затем заставляем
**сам реестр** подтвердить, что алиасы указывают на версии (а не верим картинке в UI — правило 8), и
наконец запускаем настоящую CLI-команду триажа, убеждаясь, что она действительно тянет промпт из
реестра — причём офлайн и за $0.

**Зачем это за пределами демо.** С этого момента у промпта есть история версий и возможность
откатиться или промоутить кандидата — а значит, его можно ставить под CI eval-gate (iter 2) и
автопромоушен (iter 6). Ради этого фундамента итерация и затевалась; шаги ниже показывают, что
фундамент реально стоит, а не только описан на бумаге.

Все команды копипаст-исполнимы из корня репозитория `/Users/dd/projects/pet/triagewise-lite`;
не-live шаги ничего не стоят.

Перед началом:
```bash
cd /Users/dd/projects/pet/triagewise-lite
```

## 1. Сначала убедиться, что код вообще зелёный — статический гейт

Прежде чем демонстрировать саму фичу, проверяем, что проект собран и проходит линт/типы/тесты — иначе
всё дальнейшее бессмысленно.

```bash
make check
```
**Ожидаемо:** все четыре шага зелёные —
```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 19 files already formatted
uv run mypy app                → Success: no issues found in 15 source files
uv run pytest                  → 4 passed
```

## 2. Поднять реестр — иначе промпту негде жить

Промпт теперь хранится в MLflow, поэтому, чтобы его туда положить и оттуда читать, сначала нужно
поднять control-plane backend (тот же сервис, что в iter 0, — здесь он впервые используется по делу).

```bash
make up
for i in $(seq 1 30); do curl -sf http://localhost:5050/health >/dev/null && break; sleep 1; done
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5050/health
```
**Ожидаемо:** контейнер `triagewise-lite-mlflow-1` поднимается (образ `ghcr.io/mlflow/mlflow:v3.1.1`,
хост-порт `5050` → контейнерный `5000`), `/health` возвращает `200`. Остановить потом: `make down`.

## 3. Положить промпт в реестр — это и есть «prompt-as-artifact» (НЕ live, денег не стоит)

Ключевой шаг итерации: регистрируем текст промпта как версии и вешаем на них алиасы `champion`/
`challenger`. Именно здесь промпт перестаёт быть строкой в коде и становится управляемым артефактом.

```bash
uv run python -m scripts.register_prompt
```
**Ожидаемо:** скрипт заливает шаблоны через `sync_prompts()` и печатает подробный итог — куда залил,
какая версия под каждой меткой и создалась ли новая версия:
```
Synced prompt 'triage' to MLflow registry at http://localhost:5050
  prompts:/triage@champion -> v1  (registered new version)
  prompts:/triage@challenger -> v2  (registered new version)

See the stored template text with:
  uv run python -m scripts.show_prompt champion
  or open the MLflow UI: http://localhost:5050  (Prompts -> triage)
```
Это обращение только к MLflow-реестру — **ни одного LLM-вызова**, поэтому шаг бесплатный. Команда
**идемпотентна**: повторный запуск не плодит версии, а печатает `(unchanged, alias confirmed)` и
оставляет `champion`→v1 / `challenger`→v2 на месте — новая версия появится, только если реально
изменить шаблон в `app/persistence/prompts.py`.

## 4. Посмотреть сам промпт, лежащий в реестре

«Prompt-as-artifact» стоит увидеть глазами: вытащим текст шаблона, который сейчас хранится под меткой
`champion`, прямо из реестра. Это read-only, без LLM, $0.

```bash
uv run python -m scripts.show_prompt champion
```
**Ожидаемо:** версия и сам чат-шаблон с пропусками `{{subject}}`/`{{body}}` — тот же текст, что был
константой в iter 0, теперь как хранимый артефакт:
```
prompts:/triage@champion -> v1
[
  {
    "role": "system",
    "content": "You triage Driftwood (a SaaS task-tracker) support tickets. Reply with ONLY a JSON object with keys: category (string), priority (low|medium|high|urgent), sentiment (negative|neutral|positive), needs_human (boolean), draft_reply (string). No prose, no code fences."
  },
  {
    "role": "user",
    "content": "Subject: {{subject}}\n\n{{body}}"
  }
]
```
То же самое, но в браузере: открой `http://localhost:5050`, раздел **Prompts → triage** — там видны
версии, метки и текст шаблона.

## 5. Заставить сам реестр подтвердить алиасы (правило 8, не глазами по UI)

Заявку «алиасы `champion`/`challenger` существуют и указывают на версии» проверяем запросом к самому
стору, а не картинкой в веб-интерфейсе — UI может кэшировать или приукрашивать. Спрашиваем реестр
напрямую по REST.

```bash
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" \
  | jq -r '.model_version | "champion -> v\(.version) (name=\(.name))"'
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=challenger" \
  | jq -r '.model_version | "challenger -> v\(.version) (name=\(.name))"'
```
**Ожидаемо:** реестр сам подтверждает, что алиасы указывают на разные версии —
```
champion -> v1 (name=triage)
challenger -> v2 (name=triage)
```
Разбираем ответ стора через `jq`, а не `python3 -c` (правило 9).

## 6. Прогнать настоящий триаж — и увидеть, что промпт взят из реестра (основной путь)

Это продуктовый путь целиком, ради него всё и делалось. Оператор одной командой сортирует тикет;
задача шага — убедиться, что боевая CLI-команда грузит `champion`-промпт по алиасу из реестра и при
этом по-прежнему работает офлайн за $0.

```bash
uv run python -m app.cli.main DW-001
```
**Ожидаемо:** заголовок `[DW-001] cheap (replay)` и валидный `TriageResult`. Под капотом CLI открыл
соединение с реестром, загрузил `champion`-промпт по алиасу, подставил в него текст тикета и прогнал
через `route()` в режиме `replay` — ответ пришёл из кассеты, сеть не тронута:
```json
{
  "category": "account_access",
  "priority": "high",
  "sentiment": "negative",
  "needs_human": true,
  "draft_reply": "Sorry you're locked out. I've flagged your account for a manual reset — you'll get a fresh link within a few minutes so you make your standup."
}
```
Champion-шаблон байт-в-байт повторяет промпт iter 0, поэтому ключ кассеты не изменился и закоммиченная
кассета осталась валидной — переезд промпта в реестр не потребовал ни одного платного перезаписывания.

## 7. То же подтверждение алиасов + идемпотентность, офлайн без сервера — unit-проверки (вспомогательные)

Шаг 5 проверял алиасы против живого сервера; эти тесты доказывают то же в CI, где сервера нет, плюс
что повторный `sync_prompts()` идемпотентен. Нужны, чтобы гарантии держались автоматически, а не
только при ручном прогоне демо.

```bash
uv run pytest tests/test_route_replay.py::test_champion_and_challenger_aliases_resolve \
              tests/test_route_replay.py::test_sync_prompts_is_idempotent -q
```
**Ожидаемо:** `2 passed`. Первый тест поднимает временный sqlite-реестр и проверяет, что `champion` и
`challenger` указывают на **разные** версии (тот же verify-в-сторе, что в шаге 5, но офлайн). Второй
повторяет `sync_prompts()` и убеждается, что ни одна версия не создалась заново, а метки не сдвинулись
(`created == False`). (Вспомогательные проверки: основной продуктовый путь — шаги 3–6 против живого
реестра.)

## 8. ⚠️ Записать реальную кассету (live, стоит денег) — в церемонии НЕ выполняем

Показываем ради полноты, откуда вообще берутся настоящие кассеты, но сами не запускаем: это
единственный шаг, который бьёт в сеть и тратит деньги (правило 4).

```bash
# ⚠️ live, стоит денег (правило 4): реальный вызов gpt-4.1-nano через OpenAI.
# Ключ выставить способом, который знаете только вы:
#   export OPENAI_API_KEY=sk-...        (или положить в .env)
# LLM_MODE=record uv run python -m app.cli.main DW-002
```
**Ожидаемо (если бы запускали):** реальный вызов nano с champion-промптом из реестра, ответ печатается
и сохраняется в `cassettes/<sha256>.json`; следующий `replay` для DW-002 уже офлайн. В рамках смок-
церемонии этот шаг **пропущен** как live.
