# Итерация 06b (6b) — Prefect: промоушен-петля 6a начинает крутиться сама по расписанию

> 🎯 **Цель проекта:** минимальными затратами — максимальное знакомство с инструментами LLMOps-жизненного цикла. Existence-gate, не accuracy-gate.

## Зачем это (продукт и ценность)

Продукт triagewise-lite сортирует входящие support-тикеты Driftwood — категория, приоритет, тон, нужен ли человек, черновик ответа — и держит этот LLM-конвейер под операционным контролем. Итерация 6a дала саппорт-лиду одну команду `make promote`, которая честно сравнивает кандидат-промпт с действующим и, если кандидат строго лучше, вводит его в бой. Но эту команду всё ещё надо было **вспомнить и запустить руками** — а значит, регрессия могла тихо жить в проде ровно до тех пор, пока кто-нибудь не соберётся перепрогнать гейт. Эта итерация снимает человека с петли: та же процедура eval → gate → swap теперь **сама срабатывает по расписанию** — конвейер непрерывно переоценивает себя и подхватывает лучший промпт без чьей-либо памяти и дисциплины. В продуктовых терминах: «однажды настроили промпт и молимся» окончательно превращается в «система сама следит, что в проде живёт лучший из известных промптов».

## 🧵 Что это дало резюме

Пункт north-star «**Continuous evaluation loop (LLM-аналог continuous training)**» стал демонстрируемым: `make loop` регистрирует на Prefect-сервере flow с интервальным расписанием, сервер тикает, хост-раннер исполняет тик — re-eval → gate → swap — и на сторе, где challenger лучше, alias `champion` **сам** переезжает на новую версию, что подтверждает независимый запрос к MLflow-реестру (не UI). Артефакт-доказательство: зарегистрированный Prefect-deployment `continuous-evaluation/every-interval` с активным расписанием + переехавший по расписанию alias в реестре. Это прямой LLM-аналог continuous training из sentiment-mlops.

## TL;DR (простыми словами)

В 6a петля «прогнать оба промпта → сравнить → переключить alias, если challenger лучше» уже работала, но запускалась рукой (`make promote`). Теперь та же петля обёрнута в Prefect-`@flow` и повешена на интервальное расписание: `make loop` регистрирует flow на Prefect-сервере (он в Compose, рядом с MLflow и Phoenix) и сам же его обслуживает как раннер. Раз в `LOOP_INTERVAL_SECONDS` (по умолчанию 60) сервер создаёт тик, раннер на хосте его исполняет — и на демо-сторе, где champion сброшен на v1, первый же тик переводит alias на v2. Всё офлайн и за $0 (тот же replay по derived-кассетам 6a). Дальнейшие тики — no-op: оба alias'а на одной версии, строгий гейт не находит победителя, версии не плодятся. Нового инструмента итерация не вводит — Prefect перенесён каркасом из sentiment-mlops (правило 2 не тратится); новизна только в том, что continuous-evaluation петля впервые **крутится сама**.

## Что это за инструмент

**Prefect** — это оркестратор рабочих процессов (workflow orchestrator): библиотека, которая берёт обычную Python-функцию, помечает её как «поток работы» и умеет запускать её по расписанию, следить за прогонами, собирать логи и ретраить сбои. У нас он уже был знаком по sentiment-mlops, поэтому это **не новый инструмент**, а перенос каркаса — героиня итерации не «Prefect как таковой», а сам факт, что петля стала непрерывной. Термины, которыми оперирует остальной текст:

- **flow** (`@flow`) — Python-функция, помеченная как единица оркестрации; её отдельный запуск называется **flow run** (в логах у него смешное авто-имя вроде `enthusiastic-guppy`).
- **schedule** (расписание) — правило «запускай этот flow каждые N секунд». У нас — интервальное, `interval=60`.
- **deployment** — зарегистрированная на сервере пара «flow + его расписание» (наш называется `continuous-evaluation/every-interval`). Именно deployment сервер тикает по расписанию.
- **`serve()`** — режим запуска, в котором один процесс и **регистрирует** deployment на сервере, и сам же работает **раннером**: опрашивает сервер и исполняет созданные тики. У нас `serve()` крутится на хосте (`make loop`), а расписание тикает сервер в Compose — про эту развилку ниже.
- **server / scheduler** — в Prefect 3 расписание исполняет строго **серверный** scheduler-сервис; «эфемерный» in-process режим поставляется **без** него намеренно, поэтому сервер вынесен в Compose третьим бэкендом рядом с MLflow и Phoenix.

## Поток данных

Всё начинается не с оператора, а со **времени**: раньше петлю дёргал человек командой `make promote`, теперь её дёргает расписание. Оператор один раз набирает `make loop` — и уходит; дальше причина каждого прогона — тик по расписанию, а не чьё-то решение.

`make loop` запускает `app/cli/loop.py` в режиме `serve()`. Тот делает две вещи сразу: **регистрирует** на Prefect-сервере (Compose, `:4200`) deployment `continuous-evaluation/every-interval` с интервалом `LOOP_INTERVAL_SECONDS`, и остаётся жить **раннером**, опрашивая сервер. Чтобы расписание вообще исполнялось, нужен серверный scheduler — поэтому Prefect-сервер и вынесен в Compose (в Prefect 3 in-process scheduler'а нет). Раз в интервал сервер создаёт scheduled run; раннер на хосте забирает его и исполняет тело flow `continuous_evaluation`.

А тело flow — это ровно 6a, ничего нового: чтобы сравнить промпты, нужны эталоны и реестр, поэтому boundary-функция `run_turn` (живёт в `app/cli/promote.py`, общая с ручным транспортом) заново читает `Settings`, грузит golden-сет и открывает реестр-хендл, а затем зовёт тот же workflow `run_promotion` — eval champion vs challenger по 40 golden-тикетам (replay, $0), строгий гейт, swap alias при победе challenger'а, и перечитывание alias из стора (правило 8). **Важно, где что исполняется:** расписание и стейт живут в контейнере, но **сам триаж исполняется на хосте**, в uv-env раннера — контейнер никогда не гоняет LLM и в OpenAI не ходит (граница исполнения — та же дисциплина egress'а, что у access-layer'а).

```
оператор: make loop  (один раз; replay, $0)
    │
    ▼
app.cli.loop  serve()  ─────────────┐
    │ регистрирует deployment        │ остаётся раннером (polls)
    ▼                                │
Prefect server (Compose :4200)       │
    │ scheduler: тик каждые           │
    │ LOOP_INTERVAL_SECONDS           │
    └──────────► scheduled run ───────┘
                                     │ раннер (ХОСТ, uv-env) исполняет тело flow
                                     ▼
                continuous_evaluation() ──► run_turn (boundary: Settings + golden + реестр)
                                     │
                                     ▼
                          run_promotion (workflow 6a)
                          eval champion vs challenger → gate → swap alias → verify (стор)
                                     │
                                     ▼
                    MLflow registry: alias champion → v(challenger) при победе
                    flow-run логи: scores, вердикт гейта, verify-строка, SLO-строки app.*

контейнер Prefect: только стейт + тик расписания (триаж НЕ исполняет, в OpenAI НЕ ходит)
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `make loop` → `app.cli.loop.main()` | `serve()`: регистрирует deployment + расписание на сервере и остаётся раннером на хосте | Prefect server (deployment); stdout — «serving…»-баннер |
| Prefect server (Compose `:4200`) | scheduler создаёт тик каждые `LOOP_INTERVAL_SECONDS`; хранит стейт | `./prefect-data` (volume), клиентский стейт — `./.prefect` |
| flow `continuous_evaluation` (`app/cli/loop.py`) | тело одного тика: поднимает `app.*` в INFO, зовёт `run_turn` + `print_report` | flow-run логи (scores, вердикт, verify, SLO-строки) |
| `run_turn` / `print_report` (`app/cli/promote.py`) | boundary + петля 6a + рендер отчёта — общие с `make promote`, чтобы два рассказа не разъехались | как в 6a: MLflow-реестр (swap), SLO-лог |
| `run_promotion` (workflow 6a) | eval → gate → swap → verify | MLflow Prompt Registry (alias `champion`) |

Честные оговорки — что итерация **НЕ** делает:

- **Никакой live-переоценки.** Петля живёт на derived-кассетах 6a: `replay`, $0, сеть не трогается. «Настоящий» re-eval живыми деньгами — апгрейд-путь (`LLM_MODE=record`), в скоуп не входит.
- **Новых challenger-версий никто не генерит.** Петля лишь решает, вводить ли **уже лежащий** в реестре challenger. Автогенерация кандидатов — не сюда.
- **Победа challenger'а по-прежнему сфабрикована by construction** (наследие 6a): кассеты выведены из эталонных меток, champion детерминированно ошибается на джокерах → 0.900 против 1.000. Гейту гарантированно есть что различать, но это демонстрация механики, а не измерение реальных промптов. Поэтому демо сбрасывает champion на v1 — иначе на уже-промоутнутом сторе тик честно показал бы no-op, и «переезд по расписанию» не увидеть.
- **Prefect UI существует, но не предмет.** Сервер отдаёт дашборд на `:4200`, но verify — только через MLflow-реестр (правило 8), не глазами по UI.
- **Декомпозиции петли на `@task`-и нет.** Prefect-tasks уже показаны в sentiment-mlops; здесь героиня — петля целиком, один `@flow` поверх готового `run_promotion`.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; имена функций надёжнее.

1. **Flow-обёртка петли** — `app/cli/loop.py`: `continuous_evaluation()` (:28). Это весь «новый код» инструмента — тонкий `@flow` поверх готового `run_turn`. Функция нарочно **беспараметренная**: у прогона по расписанию нет вызывающего, поэтому boundary сама перечитывает env (`Settings`), и в схему параметров deployment'а (которую `serve()` публикует на сервер) не утекает ничего не-JSON — ни реестр-хендлов, ни секретов. Первой строкой она поднимает логгер `app.*` в INFO: тик исполняется в раннер-субпроцессе, где корневым логгером владеет Prefect (WARNING), и без этого SLO-строки access-layer'а (tier+cost, iter 3) просто исчезли бы из flow-run логов.

    ```python
    @flow(name="continuous-evaluation", log_prints=True)
    async def continuous_evaluation() -> PromotionReport:
        """One scheduled turn: eval champion vs challenger -> gate -> swap -> verify in store."""
        logging.getLogger("app").setLevel(logging.INFO)
        settings = get_settings()
        report, golden_count = await run_turn(settings)   # петля 6a, общая с make promote
        print_report(report, golden_count=golden_count, mode=settings.llm_mode)
        return report
    ```

2. **Запуск serve() и защита от эфемерного режима** — `app/cli/loop.py`: `main()` (:48). Перед `serve()` `main()` проверяет `PREFECT_API_URL`: без него Prefect молча свалился бы в эфемерный сервер, который в Prefect 3 **осознанно поставляется без scheduler'а** — `serve()` выглядел бы живым, но ни один тик не наступил бы никогда. Поэтому пустой URL — это ранний выход с подсказкой «используй `make loop`», а не тихо-мёртвая петля. `serve()` регистрирует deployment детерминированно (тот же `name="every-interval"`), так что повторный запуск не плодит deployment'ы.

    ```python
    def main() -> int:
        from prefect.settings import PREFECT_API_URL
        if not PREFECT_API_URL.value():
            print("PREFECT_API_URL is not set — schedules are server-side in Prefect 3; "
                  "use `make loop` ...", file=sys.stderr)
            return 1
        settings = get_settings()
        continuous_evaluation.serve(name="every-interval", interval=settings.loop_interval_seconds)
        return 0
    ```

3. **Общее ядро двух транспортов** — `app/cli/promote.py`: `run_turn()` (:27), `print_report()` (:53). Чтобы ручной (`make promote`) и расписанный (`make loop`) рассказы одного и того же оборота не разъехались, boundary-работа и рендер отчёта вынесены сюда и импортируются в `loop.py`. `run_turn` поднимает ошибки с операторскими подсказками (нет golden → `dvc pull`, реестр не готов → `make up`): ручной транспорт мапит их в stderr + exit 1, расписанный — даёт им **уронить тик громко**, а не «промоутить на мусоре». Это чистый рефактор-вынос, поведение 6a не изменилось.

    ```python
    async def run_turn(settings: Settings) -> tuple[PromotionReport, int]:
        if not settings.golden_path.exists():
            raise FileNotFoundError(f"Golden set missing: {settings.golden_path} — run `uv run dvc pull`")
        golden = load_golden(settings.golden_path)
        client = open_registry(settings)
        ...
        report = await run_promotion(client, golden, settings=settings)
        return report, len(golden)
    ```

4. **Prefect-сервер как Compose-бэкенд** — `docker-compose.yml` (сервис `prefect`, :34). Сервер вынесен в Compose ровно потому, что в Prefect 3 расписание исполняет серверный scheduler (in-process/эфемерный режим его не гоняет). Тег образа пиннится под версию либы (`3.7.8-python3.12`), стейт — в volume `./prefect-data`, analytics off. Ключевой инвариант в комментарии: контейнер **только** хранит стейт и тикает расписание, а flow исполняется на хосте — контейнер триаж не гоняет и в OpenAI не ходит.

    ```yaml
    prefect:
      image: prefecthq/prefect:3.7.8-python3.12
      ports: ["4200:4200"]
      environment:
        - PREFECT_HOME=/data
        - PREFECT_SERVER_ANALYTICS_ENABLED=false
      volumes: ["./prefect-data:/data"]
      command: prefect server start --host 0.0.0.0 --port 4200
    ```

5. **Гигиена окружения раннера** — `Makefile`: `PREFECT_ENV` (:97) и таргет `loop` (:110). По той же посадке, что `PROMPTFOO_ENV`: клиентский стейт держим проектно-локально (`./.prefect`, gitignored), раннер целим на Compose-сервер (`PREFECT_API_URL`), analytics off, а `PREFECT_LOGGING_EXTRA_LOGGERS=app` сдаёт логгеры `app.*` Prefect'у — иначе SLO-строки tier+cost растворились бы в раннер-субпроцессе (корневой логгер там WARNING). `make up` теперь поднимает и `prefect` рядом с `mlflow`/`phoenix`.

    ```make
    PREFECT_ENV = PREFECT_HOME=$(PWD)/.prefect PREFECT_API_URL=http://localhost:4200/api \
    	PREFECT_SERVER_ANALYTICS_ENABLED=false PREFECT_LOGGING_EXTRA_LOGGERS=app
    loop:
    	$(PREFECT_ENV) uv run python -m app.cli.loop
    ```

6. **Интервал расписания** — `app/config.py`: `Settings.loop_interval_seconds` (:53), default 60. Короткий по умолчанию нарочно — демо не должно ждать минуты первого тика; сменить = одна env-строка (`LOOP_INTERVAL_SECONDS`), кода не трогая.

7. **Existence-gate петли-по-расписанию** — `tests/test_loop.py`: четыре offline-теста. Prefect-API (сервер или эфемерный) в тестах **не поднимается** — само расписание проверяет `make loop`, а не pytest; тесты зовут недекорированный `.fn()` напрямую. Ключевые: `test_flow_run_swaps_champion_in_store` (тик переставил alias — verify в сторе), `test_flow_tick_after_swap_is_noop` (второй тик стор не трогает — идемпотентность), `test_flow_fails_loud_without_golden` (тик без golden падает с dvc-подсказкой, а не «промоутит на пустом»), и `test_flow_signature_stays_json_clean` (`serve()` публикует схему параметров flow на сервер — в подписи не должно быть ничего не-JSON, и строковая аннотация не должна ронять валидацию параметров субпроцесса). Общий рецепт засева реестра вынесен в `seed_registry` (`tests/test_promotion.py`), а `flow_env` отдаёт его flow'у честным каналом — через env, тем же, что читает прогон по расписанию.

    ```python
    def test_flow_run_swaps_champion_in_store(flow_env):
        client, _ = flow_env
        challenger_version = load_triage_prompt(client, CHALLENGER).version
        report = asyncio.run(continuous_evaluation.fn())   # тело тика напрямую, без Prefect-API
        assert report.promoted
        # verify в сторе, не в отчёте (правило 8): прогон по расписанию переставил alias
        assert load_triage_prompt(client, CHAMPION).version == challenger_version
    ```
