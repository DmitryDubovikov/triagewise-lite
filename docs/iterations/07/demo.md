# Демо итерации 07 (7) — пять proof'ов жизненного цикла на одном read-only экране

Этот прогон доказывает практику **LLMOps / lifecycle management сделан легибельным**: то, что раньше собиралось пятью командами по пяти сторам, теперь видно одной read-only страницей на `localhost:8501`. Ценность за пределами демо: control plane перестал быть россыпью механизмов — у оператора есть приборный щиток над LLM-конвейером (champion-версия, вердикт гейта, дрейф, деньги, пульс петли), и «в каком состоянии система прямо сейчас» стало вопросом одного взгляда. Попутно проверяем новый маленький артефакт-стор — append-only лог гейт-вердиктов, который `run_promotion` дописывает за каждый оборот (источник карточки «последний гейт»). Весь прогон офлайн ($0): панель LLM не зовёт и ничего не пишет, live-шагов в этой итерации нет.

Все команды — из корня репо `/Users/dd/projects/pet/triagewise-lite`. Нужен golden-сет на диске (`data/golden.jsonl`; если нет — `uv run dvc pull`). Verify всегда делаем запросом к самому стору (правило 8), а не «по глазам в дашборде» — панель это рендер, истина в сторах.

### 1. Поднять стек вместе с панелью

Зачем: без поднятой панели и бэкендов доказывать нечего — это фундамент всего демо. `make up` теперь поднимает четвёртый сервис `dashboard` (:8501) рядом с MLflow/Phoenix/Prefect; `--build` пересобирает образ панели при правке её Dockerfile/requirements и кэш-no-op иначе. Реестру нужны обе стороны очной ставки — посев идемпотентен.

```bash
make up
uv run python -m scripts.register_prompt
```

**Ожидаемо:** в списке сервисов есть `dashboard`, и обе строки alias'ов из посева:

```bash
docker compose ps --format '{{.Service}} {{.Status}}'
```
```
dashboard Up ...
mlflow Up ...
phoenix Up ...
prefect Up ...
```
```
  prompts:/triage@champion -> v2  (unchanged, alias confirmed)
  prompts:/triage@challenger -> v2  (unchanged, alias confirmed)
```
(Если стор ещё не переживал промоушен, champion покажет `v1` — это не сбой; шаг 4 всё равно вернёт демо-состояние.)

### 2. Панель жива и отвечает — реальная поверхность продукта

Зачем: главный proof итерации — что read-only экран реально поднят и обслуживает страницу; это done-gate по факту существования. Спрашиваем штатный health-эндпоинт Streamlit и корень страницы через ту же поверхность, которой пользуется браузер.

```bash
curl -s localhost:8501/_stcore/health && echo
curl -s -o /dev/null -w "page HTTP %{http_code}\n" localhost:8501/
```

**Ожидаемо:**
```
ok
page HTTP 200
```
(Откроешь `http://localhost:8501` в браузере — увидишь пять карточек в две колонки: слева Prompt registry / Drift monitor / Cost-latency SLO, справа Promotion gate / Continuous-evaluation loop.)

### 3. Показать сам артефакт за карточкой промптов — не только v-номер

Зачем: карточка «Prompt registry» рисует `champion@vN` — метаданные. Чтобы демо про prompt-as-artifact было полным, печатаем **сам текст**, который лежит за этим alias'ом, через продуктовую поверхность (`show_prompt` читает тот же MLflow-реестр, что и карточка).

```bash
uv run python -m scripts.show_prompt champion | head -1
```

**Ожидаемо:** `prompts:/triage@champion -> v2` (и ниже — JSON-тело chat-промпта, который карточка на панели показывает одним номером версии).

### 4. Вернуть демо-состояние: champion на v1

Зачем: чтобы следующий гейт-оборот оставил в логе **содержательный** вердикт (`promoted:true`), стор должен быть таким, где challenger реально лучше действующего. На уже-промоутнутом сторе champion уже на v2, и оборот честно записал бы no-op. Возвращаем alias на наивную v1 (демо-сброс через persistence-слой; «разжалования» промпта в продукте нарочно нет).

```bash
uv run python -c "
from app.config import get_settings
from app.persistence.prompts import TRIAGE_PROMPT_NAME, open_registry
open_registry(get_settings()).set_prompt_alias(TRIAGE_PROMPT_NAME, 'champion', 1)
print('demo reset: champion -> v1')
"
```

**Ожидаемо:** `demo reset: champion -> v1`.

### 5. Прогнать гейт-оборот — он дописывает вердикт в лог (новая запись итерации)

Зачем: это единственная **запись** итерации 7 — `run_promotion` теперь за каждый оборот дописывает `PromotionRecord` в `logs/promotions.jsonl`, откуда карточка «Promotion gate» берёт последний вердикт. `make promote` гоняет один ручной оборот 6a (replay, $0): re-eval champion vs challenger по golden-сету, строгий гейт, swap alias, verify в сторе.

```bash
make promote
```

**Ожидаемо:** отчёт гейта — challenger побеждает, alias едет на v2:
```
  champion   v1  score=0.900
  challenger v2  score=1.000
gate: challenger wins -> champion alias swapped to v2
verify (store, rule 8): prompts:/triage@champion -> v2
```

### 6. Verify the store: гейт-лог получил валидную запись

Зачем: заставим сам артефакт подтвердить, что оборот в нём записался — jq по свежедописанной строке лога (правило 9). Это ровно та запись, которую карточка гейта показывает без перепрогона петли.

```bash
tail -1 logs/promotions.jsonl | jq '{promoted, champion_version, challenger_version, champion_version_after, golden_count, mode}'
```

**Ожидаемо:** вердикт `promoted:true`, перечитанная из стора champion-версия `champion_version_after: 2`, весь golden-сет:
```json
{
  "promoted": true,
  "champion_version": 1,
  "challenger_version": 2,
  "champion_version_after": 2,
  "golden_count": 40,
  "mode": "replay"
}
```

### 7. Идемпотентность: повторный оборот — no-op, alias не дрейфует, лог растёт трейлом

Зачем: лог — append-only трейл истории, а не реестр; повторный `make promote` после свапа обязан быть no-op в сторе (оба alias'а на v2, строгий гейт молчит), но честно дописать вторую запись — уже `promoted:false`. Прогоняем оборот второй раз и смотрим и стор, и лог.

```bash
make promote
curl -s "http://localhost:5050/api/2.0/mlflow/registered-models/alias?name=triage&alias=champion" | jq '.model_version.version'
tail -1 logs/promotions.jsonl | jq '{promoted, champion_version, challenger_version}'
```

**Ожидаемо:** champion в сторе стабилен на `"2"` (второй оборот его не двигал), а хвост лога — no-op-запись:
```
"2"
```
```json
{
  "promoted": false,
  "champion_version": 2,
  "challenger_version": 2
}
```

### 8. (вспомогательная проверка, не основной путь) Existence-gate офлайн — источники и лог без сети

Зачем: карточки панели рисует Streamlit (визуальная поверхность, curl'ом её содержимое не снять), но данные под ними дают чистые функции-источники `app/ui/sources.py` и лог `app/persistence/promotion_log.py` — их существование и корректность проверяются обычным pytest без streamlit, без стора, без сети, без LLM. Плюс механическая сверка, что пины образа панели совпадают с `uv.lock`.

```bash
uv run pytest tests/test_dashboard_sources.py -q
```

**Ожидаемо:** `11 passed` — лог дописывает и «последняя запись побеждает», толерантность к мусору/отсутствию файла, агрегаты SLO-сводки, разбор двух ответов Prefect-API, источники не тащат streamlit, имена петли совпадают с flow, пины requirements.txt == uv.lock.
