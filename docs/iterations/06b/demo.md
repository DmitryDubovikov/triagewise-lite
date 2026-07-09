# Демо итерации 06b (6b) — петля промоушена крутится сама: расписание тикает, alias переезжает без оператора

Этот прогон доказывает практику **continuous evaluation loop (LLM-аналог continuous training)**: ту же процедуру eval → gate → swap, что в 6a запускалась рукой (`make promote`), теперь **дёргает расписание**, а не человек. Ценность за пределами демо: регрессия промпта больше не ждёт, пока кто-то вспомнит перепрогнать гейт — конвейер непрерывно переоценивает себя сам и подхватывает лучший промпт, а мы лишь смотрим в реестр, что там сейчас `champion`. Весь прогон офлайн ($0): тик — тот же replay по derived-кассетам 6a, live-шагов в этой итерации нет.

Все команды — из корня репо `/Users/dd/projects/pet/triagewise-lite`. Нужен golden-сет на диске (`data/golden.jsonl`; если нет — `uv run dvc pull`). Демо двухтерминальное: **терминал A** держит петлю (`make loop`), **терминал B** сбрасывает состояние и проверяет стор.

### 1. Поднять стек (теперь и Prefect-сервер)

Расписанию нужен серверный scheduler — в Prefect 3 он живёт строго в сервере, поэтому `make up` теперь поднимает третий бэкенд `prefect` рядом с MLflow и Phoenix. Реестру нужны обе стороны очной ставки — посев идемпотентен.

```bash
make up
uv run python -m scripts.register_prompt
```

**Ожидаемо:** контейнер `prefect` в списке, обе строки alias'ов из посева:

```bash
docker compose ps --format '{{.Service}} {{.Status}}'
```
```
mlflow Up ...
phoenix Up ...
prefect Up ...
```
```
  prompts:/triage@champion -> v1  (unchanged, alias confirmed)
  prompts:/triage@challenger -> v2  (unchanged, alias confirmed)
```
(Если стор уже пережил промоушен из прошлых прогонов, `champion` покажет `v2` — это не сбой, а владение alias'ом петлёй; шаг 2 вернёт демо-состояние.)

### 2. Вернуть демо-состояние: champion на v1

Чтобы увидеть **сам** переезд по расписанию, стор должен быть таким, где challenger реально лучше действующего. На уже-промоутнутом сторе champion уже на v2, и тик честно показал бы no-op. Возвращаем alias на наивную v1 (это демо-сброс через persistence-слой; «разжалования» промпта в продукте нарочно нет).

```bash
uv run python -c "
from app.config import get_settings
from app.persistence.prompts import TRIAGE_PROMPT_NAME, open_registry
open_registry(get_settings()).set_prompt_alias(TRIAGE_PROMPT_NAME, 'champion', 1)
print('demo reset: champion -> v1')
"
```

**Ожидаемо:** `demo reset: champion -> v1`.

### 3. Запустить петлю — она сама регистрирует расписание и начинает тикать (терминал A)

Ключевой шаг done-gate. `make loop` в режиме `serve()` регистрирует на Prefect-сервере deployment `continuous-evaluation/every-interval` и остаётся раннером. Ставим короткий интервал, чтобы не ждать минуту первого тика. **Оставь этот терминал жить** — он и есть работающий раннер.

```bash
LOOP_INTERVAL_SECONDS=15 make loop
```

**Ожидаемо:** баннер serve с именем deployment'а и ссылкой на UI; затем, раз в ~15с, лог тика — оценка обоих alias'ов, вердикт гейта, verify-строка:

```
continuous-evaluation loop: every 15s (mode=replay) — Ctrl-C to stop
Your flow 'continuous-evaluation' is being served and polling for scheduled runs!
...
Flow run 'enthusiastic-guppy' - Promotion gate over 40 golden tickets (mode=replay):
Flow run 'enthusiastic-guppy' -   champion   v1  score=0.900
Flow run 'enthusiastic-guppy' -   challenger v2  score=1.000
Flow run 'enthusiastic-guppy' - gate: challenger wins -> champion alias swapped to v2
Flow run 'enthusiastic-guppy' - verify (store, rule 8): prompts:/triage@champion -> v2
Flow run 'enthusiastic-guppy' - Finished in state Completed()
```
(В логе тика также идут SLO-строки `app.llm.slo … (replay) 0ms $0.000000` — access-layer 3-й итерации виден и внутри flow-run'а, ради чего `PREFECT_LOGGING_EXTRA_LOGGERS=app` в `make loop`.)

### 4. Verify the store, не UI: alias переехал сам, по расписанию (терминал B)

Строку `verify` напечатал тот же процесс, что делал swap, — заставим сам MLflow-реестр подтвердить её независимым запросом (промпты живут в registered-models, alias-эндпоинт общий). Это и есть доказательство «continuous evaluation»: alias сменился без единой команды промоушена от человека — только `make loop` и время.

```bash
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" | jq '.model_version.version'
```

**Ожидаемо:** `"2"` — из самого стора.

### 5. Идемпотентность: дальнейшие тики стор не двигают

Расписание тикает вечно — после swap каждый тик обязан быть no-op. Смотрим лог терминала A ещё несколько тиков и перезапрашиваем стор: оба alias'а на v2, гейт отказывает, версия не растёт.

**Ожидаемо** в терминале A (следующие тики):
```
  champion   v2  score=1.000
  challenger v2  score=1.000
gate: challenger does not strictly beat champion -> no swap
verify (store, rule 8): prompts:/triage@champion -> v2
```

А в терминале B — champion всё ещё v2 и версий по-прежнему ровно две (тики не плодят версии):

```bash
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" | jq '.model_version.version'
uv run python -m scripts.show_prompt champion | head -1
```

**Ожидаемо:** `"2"`, и `prompts:/triage@champion -> v2`.

### 6. Остановить раннер — и честно про расписание (терминал A)

Жмём **Ctrl-C** в терминале A. Раннер останавливается. Важная честная оговорка: серверное расписание при этом **не гаснет** (в Prefect 3.7.8 на Python 3.14 пауза на стопе не доезжает — в логе мелькнёт `Pausing all deployments…`, но deployment остаётся активным), поэтому неотслуженные тики копятся как `Scheduled`/`Late`. Это **безвредно**: любой накопленный тик — тот же no-op промоушен, стор он не двигает (идемпотентность держит гейт, а не пауза). Убедиться, что backlog ничего не сломал:

```bash
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" | jq '.model_version.version'
```

**Ожидаемо:** по-прежнему `"2"` — сколько бы тиков ни накопилось, champion стабилен.

### 7. (вспомогательная проверка, не основной путь) Existence-gate петли офлайн, без Prefect-API

Тело тика — `continuous_evaluation.fn()` — проверяется четырьмя offline-тестами без поднятия Prefect-сервера (само расписание уже показано шагами 3–5). Бесплатно, $0, сеть не нужна.

```bash
uv run pytest tests/test_loop.py -q
```

**Ожидаемо:** `4 passed` — тик переставляет alias в сторе, второй тик no-op, тик без golden падает с dvc-подсказкой, а подпись flow остаётся JSON-чистой для `serve()`.
