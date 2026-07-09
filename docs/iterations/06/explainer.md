# Итерация 06 (6a) — промоушен-петля вручную: challenger обгоняет champion и забирает его alias

> 🎯 **Цель проекта:** минимальными затратами — максимальное знакомство с инструментами LLMOps-жизненного цикла. Existence-gate, не accuracy-gate.

## Зачем это (продукт и ценность)

Продукт triagewise-lite сортирует входящие support-тикеты Driftwood — категория, приоритет, тон, нужен ли человек, черновик ответа — и держит этот LLM-конвейер под операционным контролем. С итерации 1 в реестре рядом с рабочим промптом (`champion`) лежит кандидат получше (`challenger`), заточенный под «джокеры» — тикеты, где вежливая форма прячет негатив. Но до сих пор кандидат просто лежал: не было процедуры, которая бы честно сравнила его с действующим промптом и, если он реально лучше, ввела его в бой. Саппорт-лиду приходилось бы менять промпт руками — с риском «а вдруг хуже» и без следа, кто и почему решил. Эта итерация добавляет ровно этот кусок контроля: одна команда прогоняет оба промпта по эталонному набору из 40 размеченных тикетов, сравнивает счёт, и только если кандидат строго лучше — переключает продовый alias на него. Работающий конвейер подхватывает новый промпт на следующем же тикете, без рестарта и передеплоя.

## 🧵 Что это дало резюме

Пункт north-star «**Prompt-as-artifact + champion/challenger промоушен промптов (CD для промптов)**» стал демонстрируемым целиком, а не половиной: в итерации 1 были версии и alias'ы, теперь есть сам промоушен. Артефакт-доказательство: `make promote` печатает `champion v1 score=0.900 / challenger v2 score=1.000 → swapped`, и сам MLflow-реестр (не UI) подтверждает, что `prompts:/triage@champion` теперь указывает на v2. Это же — ручное ядро «Continuous evaluation loop»: итерации 6b останется только повесить его на расписание Prefect.

## TL;DR (простыми словами)

Раньше в реестре жили два промпта: рабочий (v1, `champion`) и кандидат (v2, `challenger`), но кандидат никогда не вводился в строй. Теперь команда `make promote` устраивает им очную ставку: оба прогоняются по golden-сету (40 эталонных тикетов), каждому считается счёт «доля угаданных меток», и если challenger строго лучше — метка `champion` переезжает на его версию прямо в реестре. Всё это в режиме `replay` по заранее заготовленным кассетам, то есть офлайн и за $0. Повторный запуск ничего не ломает: оба alias'а уже на одной версии, счёт равный, строгий гейт говорит «нет победителя». А работающий триаж подхватывает новый промпт без рестарта — он и так на каждый вызов спрашивает у реестра, куда указывает alias.

## Поток данных

Новых инструментов итерация не вводит (Prefect придёт в 6b) — она замыкает в петлю уже стоящие: реестр из итерации 1, golden-сет из итерации 2, access-layer из итерации 3.

Всё начинается с оператора, который хочет проверить, не пора ли ввести кандидата в бой, и набирает `make promote`. Чтобы сравнивать, нужны эталоны — CLI (`app/cli/promote.py`) читает golden-сет из `data/golden.jsonl` и открывает соединение с реестром (хендл рождается на boundary и дальше передаётся аргументом, как того требует правило 6). Дальше workflow `run_promotion` дважды зовёт `evaluate_alias` — сначала для `champion`, потом для `challenger`. Каждая оценка устроена без хитростей: тикет за тикетом идёт через тот же `triage_ticket`, что обслуживает продовый трафик (загрузка промпта по alias → `route()` → парсинг), а полученные метки сверяются с эталонными функцией `score_triage` — доля совпавших полей из четырёх (category, priority, sentiment, needs_human; свободный текст `draft_reply` не сверяется, у него нет эталона). В дефолтном `replay` все 80 обменов читаются из заранее заготовленных кассет — сеть не трогается, счёт $0. Затем чистая функция `should_promote` выносит вердикт: challenger обязан быть **строго** лучше — ничья оставляет действующего чемпиона. Если победил — persistence-функция `promote_challenger` переставляет alias `champion` на версию challenger'а прямо в MLflow. Напоследок workflow не верит сам себе и перечитывает alias свежим запросом к стору (правило 8) — именно эту цифру CLI печатает строкой `verify`.

```
оператор: make promote  (replay, $0)
    │
    ▼
app.cli.promote ── golden.jsonl (40 тикетов) + open_registry()
    │
    ▼
run_promotion (workflow)
    │  1. evaluate_alias(champion)  ──┐  тикет → triage_ticket → route()
    │  2. evaluate_alias(challenger) ─┤  → кассета ($0) → score_triage
    │                                 └► счёт: доля угаданных меток
    │  3. should_promote (domain): challenger строго лучше?
    │        │ да                          │ нет
    │        ▼                             ▼
    │  4. promote_challenger ──► MLflow: alias champion → v(challenger)
    │  5. перечитать alias из стора (verify, правило 8)
    ▼
stdout: scores, вердикт гейта, verify-строка

до промоушена:  champion ──► v1 (наивный промпт)   challenger ──► v2 (видит джокеров)
после:          champion ──► v2 ◄── challenger      (v1 остаётся в истории реестра)
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `app.cli.promote` (`make promote`) | открывает реестр, грузит golden, запускает петлю, печатает отчёт | stdout: scores, решение гейта, verify-строка |
| `evaluate_alias` (workflow) | гоняет 40 golden-тикетов через продовый путь `triage_ticket` и усредняет счёт | SLO-лог `logs/llm_calls.jsonl` (как любой вызов `route()`) |
| `score_triage` + `should_promote` (domain) | считают долю угаданных меток и выносят строгий вердикт | никуда (чистые функции) |
| `promote_challenger` (persistence) | переставляет alias `champion` на версию-победителя | MLflow Prompt Registry |
| `scripts.author_cassette --all` (разово, офлайн) | фабрикует кассеты golden × оба промпта из эталонных меток | `cassettes/*.json` (закоммичены) |

Честные оговорки.

- **Победа challenger'а сфабрикована by construction.** Кассеты golden-сета порождены из его же эталонных меток: challenger «отвечает» точно по эталону, champion — с двумя ошибками на каждом из 8 джокеров (тон сплющен в neutral, флаг эскалации перевёрнут). Отсюда ровно 0.900 против 1.000: гейту гарантированно есть что различать, но это демонстрация механики промоушена, а не измерение реальных промптов (пометка `# dl-lite` в `scripts/author_cassette.py`; апгрейд — `LLM_MODE=record`, живые деньги).
- **Счёт — это label-match по golden-сету, а не «accuracy продукта».** Метрика существует ради гейта (существование петли — вот ворота итерации), и никаких новых метрик качества проект не заводит.
- **Расписания ещё нет.** Петля запускается рукой оператора; «сама по расписанию» — это Prefect, итерация 6b. Judge-оценки из 5b в гейте тоже не участвуют — гейт сверяется с golden-сетом.
- **Alias `champion` сменил владельца.** До этой итерации `register_prompt` приводил оба alias'а к «как в коде»; теперь champion после первого посева принадлежит петле — повторный посев его **не откатывает** (иначе любой прогон `register_prompt` тихо разжаловал бы промоутнутый промпт).

## Карта «где в коде»

Номера строк — ориентир на момент итерации; имена функций надёжнее.

1. **Счёт и гейт** — `app/domain/promotion.py`: `score_triage()` (:20), `should_promote()` (:26). Чистая арифметика без I/O: счёт — доля совпавших полей из `LABEL_FIELDS` (:17, кортеж выводится прямо из Pydantic-схемы `GoldenLabels`, чтобы список сверяемых полей не разъехался со схемой), гейт — строгое «больше». Строгость не случайна: после swap оба alias'а указывают на одну версию, счёт равный — и петля сама собой становится идемпотентной, без специального флага «уже промоутнули».

    ```python
    LABEL_FIELDS = tuple(GoldenLabels.model_fields)  # category, priority, sentiment, needs_human

    def score_triage(result: TriageResult, expected: GoldenLabels) -> float:
        """Fraction of golden label fields the triage got right (0.0–1.0)."""
        matched = sum(getattr(result, field) == getattr(expected, field) for field in LABEL_FIELDS)
        return matched / len(LABEL_FIELDS)

    def should_promote(champion_score: float, challenger_score: float) -> bool:
        """The gate: the challenger must strictly beat the champion; a tie keeps the incumbent."""
        return challenger_score > champion_score
    ```

2. **Петля** — `app/workflow/promotion_flow.py`: `evaluate_alias()` (:41), `run_promotion()` (:62). Оценка нарочно не изобретает собственный путь вызова: каждый тикет идёт через тот же `triage_ticket`, что и продовый трафик, — со спанами, кэшем и SLO-логом, — так что гейт меряет ровно то поведение, которое получит прод после промоушена. После swap workflow перечитывает alias свежим запросом к стору и кладёт результат в отчёт полем `champion_version_after` — verify живёт внутри петли, а не только в глазах оператора.

    ```python
    async def run_promotion(client, golden, *, settings) -> PromotionReport:
        champion = await evaluate_alias(client, CHAMPION, golden, settings=settings)
        challenger = await evaluate_alias(client, CHALLENGER, golden, settings=settings)
        promoted = should_promote(champion.score, challenger.score)
        if promoted:
            promote_challenger(client, challenger.version)
        after = load_triage_prompt(client, CHAMPION).version  # verify the store, rule 8
        return PromotionReport(...)
    ```

3. **Swap и hot-reload** — `app/persistence/prompts.py`: `promote_challenger()` (:131) и `load_triage_prompt()` (:140). Сам swap — одна строка `set_prompt_alias`, вся содержательность в загрузке: раньше она шла через `client.load_prompt`, чей кэш ключуется только URI — после swap живой процесс продолжал бы получать пре-swap версию до рестарта. Теперь загрузка ходит в стор напрямую через `get_prompt_version_by_alias`, поэтому hot-reload — не отдельный механизм, а естественное следствие: следующий вызов любого работающего процесса просто видит новую цель alias'а.

    ```python
    def load_triage_prompt(client: MlflowClient, alias: str) -> PromptVersion:
        """Load the prompt version an alias points at — fresh from the store on every call.

        Deliberately not client.load_prompt: its cache is keyed by the prompt URI alone, so after
        a promotion swap it would keep serving the pre-swap version (killing hot-reload, iter 6a),
        and it bleeds across registries in a multi-registry process like the test suite."""
        return client.get_prompt_version_by_alias(TRIAGE_PROMPT_NAME, alias)
    ```

4. **Посев, который не воюет с петлёй** — `app/persistence/prompts.py`: `sync_prompts()` (:100). Семантика переопределена под новое владение: challenger остаётся code-owned (alias всегда следует за шаблоном из кода), а champion сеется только если alias'а ещё нет — существующий champion принадлежит петле, и повторный `register_prompt` его не трогает. Шаблоны матчятся по всем версиям стора (`_all_versions`, :90), так что дубликаты не плодятся.

    ```python
    for alias, template in desired:
        current = _current_version(client, alias)
        if alias == CHAMPION and current is not None:
            synced[alias] = SyncedPrompt(version=current.version, created=False)
            continue  # the promotion loop owns an existing champion alias
        version = next((pv for pv in existing if pv.template == template), None)
        ...
    ```

5. **Тонкий транспорт** — `app/cli/promote.py`: `main()` (:23) и Makefile-таргет `promote` (:90). CLI делает ровно четыре вещи: настраивает logging, проверяет пререквизиты с дружелюбными подсказками (нет golden → «run `uv run dvc pull`», пустой реестр → «run `scripts.register_prompt`»), открывает реестр-хендл и печатает отчёт петли вместе с verify-строкой из стора.

6. **Derived-кассеты** — `scripts/author_cassette.py`: `faithful_reply()` (:55), `degraded_reply()` (:61), `build_jobs()` (:73), `write_cassettes()` (:86). Скрипт-автор кассет расширен с «фикстурные тикеты под champion» до «всё × оба шаблона»: фикстурные тикеты получают кассеты и под challenger-шаблоном (иначе после промоушена продовый replay умер бы — alias-то теперь указывает на другой текст промпта), а golden-тикеты получают ответы, выведенные из собственных эталонных меток. Правило деградации champion'а детерминировано и публично — тесты импортируют его же, а не держат копию.

    ```python
    def degraded_reply(ticket: GoldenTicket) -> TriageResult:
        """What the naive champion does on a joker: takes the polite surface at face value —
        sentiment flattens toward neutral and the escalation flag flips."""
        labels = ticket.expected.model_dump()
        labels["sentiment"] = "neutral" if ticket.expected.sentiment != "neutral" else "positive"
        labels["needs_human"] = not ticket.expected.needs_human
        return TriageResult(**labels, draft_reply=_draft(ticket.expected.category))
    ```

7. **Тесты петли** — `tests/test_promotion.py`: семь offline-тестов против throwaway sqlite-реестра и tmp-кассет, авторенных тем же `build_jobs`/`write_cassettes`, что и закоммиченные. Ключевые: `test_promotion_swaps_champion_alias` (happy-path + verify в сторе), `test_promotion_rerun_is_noop` (идемпотентность), `test_sync_after_promotion_does_not_roll_back` (владение alias'ом), `test_hot_reload_same_process` (один процесс, один хендл: до swap триаж отвечает по-чемпионски мимо джокера, после — челленджерским чтением скрытого негатива) и guard `test_committed_cassettes_cover_golden_for_both_prompts` (каждому golden-тикету — кассета под ОБОИМИ шаблонами, иначе `make promote` умрёт на середине; в CI скипается вместе с golden-сетом).
