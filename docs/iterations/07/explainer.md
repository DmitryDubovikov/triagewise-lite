# Итерация 07 (7) — Streamlit control-plane dashboard: пять живых proof'ов жизненного цикла на одном экране

> 🎯 **Цель проекта:** минимальными затратами — максимальное знакомство с инструментами LLMOps-жизненного цикла. Existence-gate, не accuracy-gate.

## Зачем это (продукт и ценность)

Продукт triagewise-lite сортирует входящие support-тикеты Driftwood — категория, приоритет, тон, нужен ли человек, черновик ответа — и держит этот LLM-конвейер под операционным контролем. За шесть предыдущих итераций контроль накопился, но расползся: чтобы узнать, всё ли в порядке, саппорт-лид должен был помнить пять разных команд и ходить по пяти разным сторам — `show_prompt` за версией промпта в MLflow, лог гейта, `drift-report` за дрейфом в Phoenix, `slo-report` за деньгами, Prefect UI за петлёй. Каждый ответ отдельно, разным инструментом, из своей памяти. Эта итерация ничего нового в сам жизненный цикл не добавляет — она делает уже существующий control plane **легибельным**: одна read-only страница на `localhost:8501` собирает все пять живых proof'ов в один экран, так что «в каком состоянии мой LLM-конвейер прямо сейчас» становится вопросом одного взгляда, а не пяти команд. В продуктовых терминах: у оператора появился приборный щиток над конвейером — он видит champion-версию, вердикт последнего гейта, статус дрейфа, счёт по деньгам и пульс петли, не разбирая систему по частям.

## 🧵 Что это дало резюме

Пункт north-star №1 «**LLMOps / LLM lifecycle management**» (зонтичный термин) стал **демонстрируемым как связное целое**, а не как россыпь отдельных механизмов: control-plane dashboard показывает пять доказательств жизненного цикла — реестр промптов с alias'ами, гейт-вердикт, дрейф-монитор, cost/latency SLO и continuous-evaluation петлю — на одном экране. Артефакт-доказательство: живая страница `localhost:8501` (health `ok`), где каждая карточка — свежее чтение своего стора. **Честность против раздувания:** Streamlit здесь — рендер-вехикул, отдельной резюме-строки он не даёт (в отличие от promptfoo/Phoenix/MLflow-реестра); героиня — видимый control plane, а не Streamlit как таковой. Это прямо зафиксировано в ROADMAP и спеке.

## TL;DR (простыми словами)

Раньше пять proof'ов жизненного цикла жили каждый в своём инструменте, и «как там мой конвейер» собиралось из пяти команд по разным сторам. Теперь есть один read-only экран (Streamlit, отдельный Compose-сервис на `:8501`), который на каждый refresh заново читает все пять сторов и рисует пять карточек: какая версия промпта под `champion`/`challenger` (MLflow-реестр), чем кончился последний гейт-оборот (новый лог `logs/promotions.jsonl`), есть ли дрейф категорий (Phoenix), сколько потрачено денег и как с cache/latency (SLO-лог), и крутится ли петля по расписанию (Prefect REST). Панель **только читает** — ничего не пишет, LLM не зовёт, источником истины остаются сторы (правило 8). Всё офлайн, $0. Нового инструмента для резюме итерация не вводит — Streamlit это рендер; ценность в том, что control plane стал виден одним взглядом. Попутно появился один маленький новый артефакт-стор: append-only лог гейт-вердиктов, который `run_promotion` теперь дописывает за каждый оборот, чтобы карточке гейта было что показать без перепрогона петли.

## Что это за инструмент

**Streamlit** — это библиотека для «дашбордов на чистом Python»: пишешь обычный скрипт сверху вниз (`st.title(...)`, `st.metric(...)`, `st.dataframe(...)`), а Streamlit превращает его в веб-страницу и сам крутит мини-сервер. Никакого HTML/JS и никакого фронтенд-стека — страница это просто исполняемый скрипт. Ключевая для нас особенность — **модель перепрогона (rerun):** при каждом взаимодействии (клик по кнопке, загрузка страницы) Streamlit **исполняет весь скрипт заново** сверху вниз. Нам это ровно на руку: раз скрипт перечитывается целиком, каждая карточка на каждый refresh заново читает свой стор — панель по построению не может показать протухший кэш, она всегда рисует то, что в сторе сейчас. Термины, которыми оперирует остальной текст: **rerun** — полный повторный прогон скрипта на каждое действие; **`st.container(border=True)`** — прямоугольная рамка-карточка, в которую мы кладём один proof; **headless-режим** — Streamlit-сервер без попытки открыть браузер (так он и живёт в контейнере). Streamlit у нас — **рендер-вехикул, не резюме-строка** (правило «честность против раздувания»): он есть только в образе панели (`dashboard/requirements.txt`), в uv-env его нет, и поэтому ни один pytest его не импортирует.

## Поток данных

Всё начинается с оператора, которому нужен один взгляд на состояние конвейера. Он открывает `http://localhost:8501` в браузере (или жмёт кнопку «↻ re-read stores» на уже открытой странице) — и это событие запускает поток: Streamlit исполняет скрипт `app/ui/dashboard.py` целиком сверху вниз. Чтобы нарисовать пять карточек, скрипту нужны свежие данные из пяти сторов — поэтому на boundary страницы (`dashboard.py`) он открывает по хендлу на каждый стор (MLflow-client, Phoenix-client, httpx на Prefect, пути к JSONL-логам) и передаёт их вниз, в функции-источники `app/ui/sources.py`. Источники ничего не рисуют и ничего не пишут — каждый читает **один** стор и возвращает чистую структуру (`NamedTuple`); рендер (`st.metric`/`st.dataframe`) остаётся наверху, в `dashboard.py`. Это тот же шов, что во всём проекте: транспорт тонкий, источники чистые, зависимости приходят аргументами (правило 6).

Пять карточек читают пять разных сторов, каждый — след своей более ранней итерации:

```
оператор: открывает localhost:8501  (или жмёт «↻ re-read stores»)
    │
    ▼
Streamlit rerun: исполняет app/ui/dashboard.py целиком
    │  boundary: открывает хендлы на сторы, зовёт app/ui/sources
    │
    ├─► prompt_statuses(mlflow-client) ──────► MLflow registry :5050 → champion/challenger версии
    ├─► last_promotion(promotions.jsonl) ────► logs/promotions.jsonl → последний гейт-вердикт
    ├─► drift_status(phoenix-client) ────────► Phoenix :6006 spans → дрейф категорий base vs postrelease
    ├─► slo_summary(llm_calls.jsonl) ────────► logs/llm_calls.jsonl → calls / cost / breaches / cache
    └─► fetch_loop_status(httpx) ────────────► Prefect REST :4200 → расписание + последний flow-run
    │
    ▼
пять карточек st.container(border=True); мёртвый стор → warning + подсказка, страница не падает

панель НИЧЕГО не пишет и LLM не зовёт: сторы остаются истиной (правило 8), egress — host-only
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| оператор → `localhost:8501` / кнопка «↻» | триггерит rerun — Streamlit гоняет `dashboard.py` заново | ничего (read-only) |
| `prompt_statuses` (`app/ui/sources.py`) | читает, на какую версию смотрят alias'ы `champion`/`challenger` | — (только читает MLflow-реестр) |
| `last_promotion` (`app/persistence/promotion_log.py`) | берёт последнюю валидную запись гейт-лога | — (читает `logs/promotions.jsonl`) |
| `drift_status` (`app/ui/sources.py`) | тянет спаны из Phoenix, считает дрейф категорий (переиспользует `category_drift`) | — (читает Phoenix span-store) |
| `slo_summary` (`app/ui/sources.py`) | сворачивает per-call SLO-лог в агрегаты (calls, cost, breaches, cache-rate) | — (читает `logs/llm_calls.jsonl`) |
| `fetch_loop_status` (`app/ui/sources.py`) | голым httpx GET/POST спрашивает Prefect про deployment + последний run | — (читает Prefect REST API) |
| `run_promotion` (`app/workflow/promotion_flow.py`) | **единственная запись итерации:** дописывает `PromotionRecord` за каждый гейт-оборот | `logs/promotions.jsonl` (append-only) |

Честные оговорки — что итерация **НЕ** делает:

- **Панель не источник истины и ничего не мутирует.** Она только рисует то, что в сторах; verify по-прежнему делается запросом к самому стору (правило 8), а не «по глазам в дашборде». Кнопка «↻» ничего не промоутит и не запускает — она лишь заставляет скрипт перечитать сторы.
- **Панель не ходит в OpenAI.** Ни одна карточка не зовёт LLM; egress остаётся host-only, дисциплина LiteLLM (правило 5) не тронута — контейнер панели вообще не на LLM-пути.
- **Новой резюме-практики нет.** Streamlit — рендер; никакой строки в резюме он не добавляет. Единственный новый **артефакт** — append-only лог гейт-вердиктов, и он тоже лог, а не реестр: alias-истина остаётся в MLflow.
- **Дашборд читает host-логи через read-only mount.** `./logs` и `./app` монтируются в контейнер `:ro` — это задокументированное исключение из «нет общей ФС» (шов был про artifact-path-mismatch, не про read-only рендер append-only логов). Пишет в эти файлы только хост.
- **Карточки деградируют, а не падают.** Если стор недоступен (backend не поднят, лог ещё пуст), карточка показывает warning с операторской подсказкой («подними `make up`», «прогони `make traffic`») — соседние карточки при этом живут.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; имена функций надёжнее.

1. **Персист гейт-вердикта — единственная запись итерации** — `app/workflow/promotion_flow.py`: хвост `run_promotion()` (:76). После свапа (или его отказа) и перечитывания alias из стора (`after`) оборот дописывает одну запись `PromotionRecord` в лог. Важно, **где** это стоит: после `after = load_triage_prompt(...)`, то есть запись несёт champion-версию, перечитанную из стора уже **после** возможного свапа (правило 8) — карточка гейта показывает не то, что оборот собирался сделать, а то, что реально оказалось в реестре. Запись общая для обоих транспортов (`make promote` и Prefect-тик) — оба зовут `run_promotion`, поэтому лог одинаково наполняется что рукой, что расписанием.

    ```python
    if promoted:
        promote_challenger(client, challenger.version)
    after = load_triage_prompt(client, CHAMPION).version
    # Persist the verdict (iter 7): every turn leaves one record in the promotion log ...
    log_promotion(
        PromotionRecord(
            ts=datetime.now(UTC).isoformat(timespec="milliseconds"),
            champion_version=champion.version, champion_score=champion.score,
            challenger_version=challenger.version, challenger_score=challenger.score,
            promoted=promoted, champion_version_after=after,
            golden_count=len(golden), mode=settings.llm_mode,
        ),
        settings,
    )
    ```

2. **Гейт-лог как стор** — `app/persistence/promotion_log.py`: `PromotionRecord` (:20), `log_promotion` (:32), `last_promotion` (:39). Append-only JSONL рядом с SLO-логом, та же посадка (правило 9: jq-friendly). `log_promotion` дописывает одну строку; `last_promotion` толерантно сворачивает файл до самой свежей парсящейся записи — рваная или чужая строка пропускается, а не роняет чтение (это нужно карточке: панель деградирует до последней записи, которую ещё может прочесть). Схема несёт обе стороны очной ставки (версии + скоры), вердикт `promoted`, перечитанную `champion_version_after`, размер golden-сета и mode.

    ```python
    class PromotionRecord(BaseModel):
        ts: str
        champion_version: int; champion_score: float
        challenger_version: int; challenger_score: float
        promoted: bool
        champion_version_after: int  # fresh store read after the (possible) swap, rule 8
        golden_count: int
        mode: str  # replay | record | live

    def last_promotion(path: Path) -> PromotionRecord | None:
        latest: PromotionRecord | None = None
        for record in iter_records(path, PromotionRecord):
            latest = record
        return latest
    ```

3. **Общий толерантный ридер JSONL** — `app/persistence/jsonl.py`: `iter_records()` (:20). У всего лог-семейства проекта (SLO-звонки, гейт-обороты) один и тот же диалект чтения: пустая, рваная или чужая строка пропускается, никогда не фатальна. Эта политика написана один раз генератором, и над ним фолдятся и `last_promotion`, и `slo_summary` панели — вместо двух копий `try/except ValidationError`. Отсутствующий файл = пустой поток (не ошибка): карточка на пустом логе показывает «no … yet», а не падает.

    ```python
    def iter_records(path: Path, model: type[M]) -> Iterator[M]:
        """Yield every parseable `model` record from a JSONL file ([] when it doesn't exist)."""
        if not path.exists():
            return
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    yield model.model_validate_json(line)
                except ValidationError:
                    continue
    ```

4. **Пять функций-источников, чистых от рендера** — `app/ui/sources.py`: `prompt_statuses` (:40), `drift_status` (:54), `slo_summary` (:73), `parse_loop_status` (:95) + `fetch_loop_status` (:109). По одной функции на карточку, каждая читает **один** стор и возвращает `NamedTuple` — рендер (`st.*`) сюда не проникает, поэтому модуль тестируется обычным pytest без streamlit, без сети, без стора. Prefect-чтение нарочно расколото: чистый разбор двух ответов API (`parse_loop_status`) отделён от httpx-I/O (`fetch_loop_status`) — разбор проверяется юнит-тестом, а в образ панели **не тащится сама либа prefect** (только голый httpx GET/POST по двум эндпоинтам). Хендлы приходят аргументами — открываются на boundary панели (правило 6).

    ```python
    def fetch_loop_status(settings: Settings) -> LoopStatus:
        """Deployment schedule + newest flow run over the plain Prefect REST API."""
        import httpx  # lazy at the seam, like every store client in this app
        deployment = None
        with httpx.Client(base_url=settings.prefect_api_url.rstrip("/"), timeout=5) as client:
            resp = client.get(f"/deployments/name/{LOOP_FLOW}/{LOOP_DEPLOYMENT}")
            if resp.status_code == 200:
                deployment = resp.json()
            elif resp.status_code != 404:  # 404 = loop never registered — a state, not an error
                resp.raise_for_status()
            runs = client.post("/flow_runs/filter", json={...})
            runs.raise_for_status()
        return parse_loop_status(deployment, runs.json())
    ```

5. **Тонкий транспорт-страница** — `app/ui/dashboard.py`: `card()` (:35) + пять `render_*` + раскладка в две колонки (:134). `card()` — единственная общая обвязка: оборачивает рендер одного proof'а в рамку и ловит **любой** сбой стора в один и тот же деградированный вид (warning + операторская подсказка), чтобы мёртвый backend ронял карточку, а не страницу. Каждый `render_*` открывает хендл своего стора **на этом boundary** (`open_registry(settings)`, `Client(base_url=...)`), зовёт источник и рисует. Store-клиенты (mlflow, phoenix) импортируются лениво прямо в рендере — тот же приём отложенного импорта, что во всём проекте.

    ```python
    def card(title: str, render: Callable[[], None], hint: str) -> None:
        """One proof, one container; a dead backend degrades the card, not the page."""
        with st.container(border=True):
            st.subheader(title)
            try:
                render()
            except Exception as exc:  # any store failure = the same degraded card
                st.warning(f"unavailable: {exc}")
                st.caption(hint)
    ```

6. **Образ панели как отдельный lock** — `dashboard/Dockerfile` + `dashboard/requirements.txt`. Отдельный Compose-сервис на pinned python-base; deps панели пиннятся собственным маленьким `requirements.txt` — это lock образа, аналог `uv.lock`. Версии, общие с хост-env (`mlflow-skinny`, `pydantic`, `httpx`, phoenix-client), пиннятся на **те же числа**, что в `uv.lock`, — панель читает сторы тем же клиентским диалектом, каким приложение их пишет; это проверяется механически тестом `test_dashboard_image_pins_match_uv_lock`. Код приложения в образ **не вшит** — Compose монтирует `./app` read-only, так что панель всегда рендерит рабочее дерево без пересборки. `PYTHONPATH=/srv` прописан явно: streamlit — console-script, он кладёт на `sys.path` каталог самого скрипта, а не cwd, поэтому смонтированный пакет `app` надо назвать по абсолютному пути.

    ```dockerfile
    FROM python:3.12.13-slim
    ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv \
        STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
    WORKDIR /srv
    COPY requirements.txt /srv/requirements.txt
    RUN pip install --no-cache-dir -r requirements.txt
    EXPOSE 8501
    CMD ["streamlit", "run", "app/ui/dashboard.py",
         "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
    ```

7. **Compose-сервис `dashboard`** — `docker-compose.yml` (сервис `dashboard`, :50). Панель ходит в MLflow/Phoenix/Prefect **по compose-сети** (env-URL'ы на имена сервисов: `http://mlflow:5000`, `http://phoenix:6006`, `http://prefect:4200/api`), а host-логи получает через read-only mount (`./logs:/srv/logs:ro`, `./app:/srv/app:ro`). `make up` теперь поднимает `dashboard` рядом с тремя бэкендами (`--build`, чтобы образ пересобирался при правке Dockerfile/requirements и был кэш-no-op иначе). Инвариант в комментарии: контейнер **read-only** и в OpenAI не ходит.

    ```yaml
    dashboard:
      build: ./dashboard
      ports: ["8501:8501"]
      environment:
        - MLFLOW_TRACKING_URI=http://mlflow:5000
        - PHOENIX_ENDPOINT=http://phoenix:6006
        - PREFECT_API_URL=http://prefect:4200/api
      volumes:
        - ./app:/srv/app:ro
        - ./logs:/srv/logs:ro
    ```

8. **Общие имена петли, чтобы flow и панель не разъехались** — `app/config.py`: `LOOP_FLOW`/`LOOP_DEPLOYMENT` (:19). Панель читает петлю по имени через REST (в её образе нет prefect-либы), а flow регистрирует себя тем же именем — если бы имена жили в двух местах, они бы разъехались молча. Поэтому обе константы вынесены в prefect-free `config.py` и импортируются и flow'ом (`app/cli/loop.py`), и REST-ридером (`app/ui/sources.py`); тест `test_loop_names_match_the_flow` держит `continuous_evaluation.name == LOOP_FLOW`.

    ```python
    LOOP_FLOW = "continuous-evaluation"
    LOOP_DEPLOYMENT = "every-interval"
    ```
