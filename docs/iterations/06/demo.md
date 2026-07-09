# Демо итерации 06 (6a) — challenger обгоняет champion, alias переезжает, прод подхватывает без рестарта

Этот прогон доказывает практику **champion/challenger промоушен промптов (CD для промптов)** — ручное ядро continuous-evaluation петли: кандидат-промпт сравнивается с действующим по эталонному golden-сету, строгий гейт решает «вводить ли в бой», swap происходит в самом реестре, и работающий конвейер подхватывает новый промпт на следующем вызове — без рестарта и передеплоя. Ценность за пределами демо: смена продового промпта перестаёт быть ручной правкой «на удачу» — это воспроизводимая процедура со счётом, вердиктом и следом в реестре. Весь прогон офлайн ($0): оба промпта replay'ятся по закоммиченным derived-кассетам, live-шагов в этой итерации нет вовсе.

Все команды выполняются из корня репо `/Users/dd/projects/pet/triagewise-lite`. Нужен golden-сет на диске (`data/golden.jsonl`; если отсутствует — `uv run dvc pull`).

### 1. Поднять реестр и посеять промпты

Петле нужны обе стороны очной ставки в реестре: v1 (наивный champion) и v2 (challenger, натасканный на джокеров). Посев идемпотентен — на уже засеянном сторе он ничего не пересоздаёт.

```bash
make up
uv run python -m scripts.register_prompt
```

**Ожидаемо:** обе строки alias'ов; на свежем сторе — `registered new version`, на уже засеянном — `unchanged, alias confirmed`:

```
Synced prompt 'triage' to MLflow registry at http://localhost:5050
  prompts:/triage@champion -> v1  (unchanged, alias confirmed)
  prompts:/triage@challenger -> v2  (unchanged, alias confirmed)
```

(Если стор уже пережил промоушен из прошлых прогонов, первая строка покажет `champion -> v2` — это не откат не случился, а владение alias'ом петлёй; шаг 2а вернёт демо-состояние.)

### 2. Посмотреть сами артефакты: чем кандидат отличается от действующего

Промоушен без взгляда на сам промпт — кот в мешке. Реестр хранит текст обеих версий; спрашиваем его самого (read-only, $0).

```bash
uv run python -m scripts.show_prompt champion
uv run python -m scripts.show_prompt challenger
```

**Ожидаемо:** champion — базовый системный промпт триажа; challenger — тот же текст плюс хвост про джокеров:

```
prompts:/triage@challenger -> v2
[
  {
    "role": "system",
    "content": "You triage Driftwood (a SaaS task-tracker) support tickets. ... Watch for tickets
that are polite on the surface but negative underneath, and for ambiguous categories — escalate
(needs_human=true) when unsure."
  },
  ...
]
```

### 2а. (вспомогательная, не основной путь) Вернуть демо-состояние, если champion уже промоутнут

Промоушен персистентен: на сторе, где петля уже бегала, champion уже указывает на v2, и шаг 3 покажет no-op вместо swap. Чтобы увидеть сам переезд, вернём alias на v1 (это именно демо-сброс через persistence-слой; в реальной жизни «разжаловать» промпт — отдельное решение, которого в продукте нарочно нет).

```bash
uv run python -c "
from app.config import get_settings
from app.persistence.prompts import TRIAGE_PROMPT_NAME, open_registry
open_registry(get_settings()).set_prompt_alias(TRIAGE_PROMPT_NAME, 'champion', 1)
print('demo reset: champion -> v1')
"
```

**Ожидаемо:** `demo reset: champion -> v1`.

### 3. Сам промоушен: eval → gate → swap

Ключевой шаг done-gate. Оба alias'а прогоняются по 40 golden-тикетам через продовый путь триажа (replay, $0), строгий гейт сравнивает счёт, и challenger забирает alias `champion`.

```bash
make promote
```

**Ожидаемо** (счёт детерминирован: champion теряет по 2 метки из 4 на каждом из 8 джокеров → 0.900):

```
Promotion gate over 40 golden tickets (mode=replay):
  champion   v1  score=0.900
  challenger v2  score=1.000
gate: challenger wins -> champion alias swapped to v2
verify (store, rule 8): prompts:/triage@champion -> v2
```

### 4. Verify the store, не UI: alias действительно переехал

Строка `verify` из шага 3 напечатана тем же процессом, что делал swap, — заставим сам реестр подтвердить её независимым запросом (MLflow REST; промпты живут в registered-models со специальным тегом, alias-эндпоинт общий).

```bash
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" | jq .
```

**Ожидаемо:** версия `2` из самого стора:

```json
{
  "model_version": {
    "name": "triage",
    "version": "2",
    ...
  }
}
```

### 5. Идемпотентность: повторная петля и повторный посев ничего не двигают

Петля обязана быть перезапускаемой (в 6b её будет дёргать расписание). После swap оба alias'а на v2, счёт равный — строгий гейт оставляет действующего. А повторный посев не смеет откатить промоушен.

```bash
make promote
uv run python -m scripts.register_prompt
```

**Ожидаемо:** от `make promote` — равные счета и отказ гейта; от посева — champion остаётся на v2:

```
  champion   v2  score=1.000
  challenger v2  score=1.000
gate: challenger does not strictly beat champion -> no swap
verify (store, rule 8): prompts:/triage@champion -> v2
...
  prompts:/triage@champion -> v2  (unchanged, alias confirmed)
```

### 6. Прод подхватил новый промпт без рестарта

То, ради чего всё затевалось: обычная продовая команда триажа (та же, что в итерациях 0–1) теперь молча работает промоутнутым промптом — alias-fresh загрузка на каждом вызове, никакого передеплоя. Кассеты под challenger-шаблон для фикстурных тикетов заготовлены заранее, так что replay жив и после swap.

```bash
uv run python -m app.cli.main DW-001
```

**Ожидаемо:** обычный разбор тикета (`[DW-001] cheap (replay)` + JSON с пятью полями) — конвейер не заметил смены промпта, что и требовалось.

### 7. (вспомогательная, не основной путь) Hot-reload внутри одного процесса

Шаг 6 показывает подхват между запусками CLI; строгую версию — «один процесс, один registry-хендл, prompt меняется между двумя вызовами без переоткрытия» — держит offline-тест на throwaway-реестре.

```bash
uv run pytest tests/test_promotion.py::test_hot_reload_same_process -q
```

**Ожидаемо:** `1 passed` — до swap триаж джокера отвечает по-чемпионски (`sentiment=neutral`, мимо), сразу после swap тот же процесс читает скрытый негатив (`sentiment=negative`).
