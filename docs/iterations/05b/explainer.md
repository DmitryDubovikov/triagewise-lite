# Итерация 05b — Phoenix online LLM-as-judge: качество триажа оценивается прямо на трафике

> 🎯 **Цель проекта:** минимальными затратами — максимальное знакомство с инструментами LLMOps-жизненного цикла. Existence-gate, не accuracy-gate.

## Зачем это (продукт и ценность)

Продукт triagewise-lite сортирует входящие support-тикеты Driftwood — категория, приоритет, тон, нужен ли человек, черновик ответа — и держит этот LLM-конвейер под операционным контролем. После 5a конвейер оставляет след от каждого разбора и умеет замечать, что распределение ответов «поехало», — но никто не отвечал на вопрос «а сами ответы вообще *правильные*?». Дрейф-монитор увидит новую категорию, но пропустит тихую деградацию: конвейер может месяц уверенно раскладывать благодарности в `feature_request`, и ни одна метрика 5a не моргнёт. Эта итерация добавляет саппорт-лиду ровно этот кусок контроля: вторая, более сильная модель выборочно перечитывает уже разобранные тикеты и ставит каждому вердикт «triage correct / incorrect» с объяснением — прямо рядом с записью самого разбора. На нашем живом прогоне судья немедленно окупился: поймал «джокера» golden-сета — позитивный отзыв о dark mode, который триаж уверенно (и ошибочно) записал в `feature_request`.

## 🧵 Что это дало резюме

Пункт north-star «**Online evaluation / LLM-as-judge в проде**» стал демонстрируемым: `make judge` (live) сэмплирует затрейсенный трафик, судит его `smart`-тиром через `phoenix.evals` и пишет вердикты в Phoenix span-annotations; `make judge-report` спрашивает стор Phoenix (не UI) и печатает `{"labels": {"correct": 52, "incorrect": 4}}` — оценки судьи лежат рядом с трейсами, которые они оценивают. Вместе с 5a это закрывает строку ROADMAP #5 целиком.

## TL;DR (простыми словами)

После 5a каждый разбор тикета оставлял в Phoenix спан — запись «что вошло и что вышло», но записи никто не перечитывал. Теперь есть команда `make judge`: она забирает эти записи, детерминированно выбирает часть (по умолчанию половину трафика), и сильная модель (`gpt-4.1`, тир `smart`) выносит по каждой вердикт — correct или incorrect, с объяснением почему. Вердикт приклеивается к той же записи в Phoenix, так что в UI оценка видна прямо рядом с разбором. Уже осуждённые записи повторно не судятся — второй запуск подряд не делает ни одного LLM-вызова и стоит $0. Это единственная итерация проекта, где демо принципиально живое: судья владеет своим вызовом и через кассеты не ходит.

## Что это за инструмент

Итерация не вводит новый сервис — она открывает две новые грани уже стоящего Arize Phoenix.

**LLM-as-judge** — это практика, а не пакет: качество ответов LLM оценивает другая (обычно более сильная) LLM, потому что на живом трафике эталонной разметки нет и сравнивать «с правильным ответом» не с чем. *Online evaluation* — та же идея, применённая к продакшен-трафику: оценивается не офлайн-бенчмарк (это делает promptfoo в итерации 2), а выборка реальных запросов, уже обслуженных системой. Оценка идёт асинхронно, отдельным процессом — путь пользовательского запроса она не тормозит.

**`phoenix.evals`** (пакет `arize-phoenix-evals`, у нас серия 3.x) — библиотека судейства из экосистемы Phoenix. Ключевой словарь: *evaluator* — объект «промпт-шаблон + LLM + допустимые ответы», который собирается фабрикой `create_classifier(...)`; *choices* — закрытый список меток с числовыми баллами (у нас `{"correct": 1.0, "incorrect": 0.0}`), в который ответ судьи обязан попасть — библиотека добивается этого через structured output, свободный текст судьи не просочится; *LLM wrapper* — обёртка `LLM(provider="openai", model=...)`, которая делегирует вызов уже установленному SDK провайдера. Судья «владеет своим вызовом»: он не ходит через наш `route()` и кассеты, поэтому каждый его запуск — живые деньги (это заранее благословлённое исключение из tech-decisions, как у promptfoo).

**Span annotations** — механизм Phoenix «приклеить оценку к спану»: запись с именем, меткой, баллом и объяснением, которая хранится в сторе рядом со спаном и показывается в UI на его панели. Наша аннотация называется `triage_quality`, её `annotator_kind` — `LLM` (Phoenix различает, кто оценивал: человек, код или модель). Именно аннотации дают формулировку done-gate «оценки judge видны рядом с трейсами» — и заодно память судьи: у кого аннотация уже есть, того повторно не судим.

## Поток данных

Всё начинается с оператора, который хочет узнать, не деградировал ли триаж на живом потоке, и набирает `make judge` (это live-команда — Makefile и CLI оба напомнят про ключ, а стоимость на свежем сторе с одной парой пачек — центы). Чтобы судить, нужно знать, что вообще происходило, — поэтому judge-workflow первым делом читает из Phoenix все спаны `triage_ticket` (те самые, что оставила итерация 5a). Судить всё подряд дорого и не нужно — трафик сэмплируется: детерминированный хеш от `ticket_id` решает, попадает ли тикет в выборку (`JUDGE_SAMPLE_RATE=0.5` — половина), и тот же хеш даст тот же ответ в любом следующем запуске. Чтобы не платить дважды за одно и то же, workflow тут же спрашивает у Phoenix аннотации `triage_quality`: у кого они уже есть, тот выбывает. По каждому выжившему кандидату evaluator из `phoenix.evals` задаёт `smart`-модели один вопрос — «вот тикет, вот выход триажа: correct или incorrect?» — и вердикт с объяснением улетает обратно в Phoenix аннотацией на исходный спан. Когда оператор хочет сводку, он набирает `make judge-report`: отчёт читает аннотации из стора (не из UI) и печатает счётчики меток и повердиктный список.

```
оператор: make judge  (⚠️ live)
    │
    ▼
app.cli.judge ──► judge_traffic (workflow)
    │                 │
    │   1. fetch_triage_spans ─────────► Phoenix :6006 (спаны 5a)
    │   2. fetch_judge_annotations ────► Phoenix (кто уже осуждён — выбывает)
    │   3. select_for_judgement (domain: hash-сэмпл + skip)
    │   4. judge_candidates ──────────► OpenAI (smart-тир, phoenix.evals)
    │   5. log_verdicts ──────────────► Phoenix (annotation triage_quality
    ▼                                            на исходный спан)
stdout: [span] correct/incorrect: объяснение

оператор: make judge-report
    │
    ▼
scripts.judge_report ──► Phoenix REST (аннотации) ──► JSON {labels, verdicts} + exit-код
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| `app.cli.judge` (`make judge`, ⚠️ live) | собирает поток: спаны → сэмпл → судья → аннотации | stdout: вердикт+объяснение на спан, итоговая строка |
| `select_for_judgement` + `sampled` (domain) | детерминированно выбирает, кого судить, и выкидывает уже осуждённых | никуда (чистые функции) |
| `judge_candidates` (`phoenix.evals`) | один LLM-вызов `smart`-тиром на кандидата: correct/incorrect + объяснение | никуда сам по себе (вердикты возвращает workflow) |
| `log_verdicts` | приклеивает вердикты к исходным спанам | Phoenix, аннотация `triage_quality` (label, score, explanation) |
| `scripts.judge_report` (`make judge-report`) | читает аннотации из стора и агрегирует | stdout: JSON-отчёт; exit 0 = осуждённые спаны есть |

Честные оговорки.

- **Судья оценивает спаны, а не уникальные тикеты.** Трейсы append-only: если `make traffic` гоняли четыре раза, каждый сэмплированный тикет лежит в сторе четырьмя спанами, и судья честно оплатит все четыре (наш живой прогон: 84 спана → 56 вызовов ≈ $0.11 вместо «14 тикетов ≈ $0.03»). Для online-оценки это осмысленная семантика — спан и есть событие трафика, — но для кошелька урок: см. learnings.
- **Судья не абсолютная истина.** Это та же LLM-механика с теми же слабостями; его вердикты — сигнал для человека (и вход будущих гейтов), а не приговор. Accuracy самого судьи мы не меряем — existence-gate.
- **Никакой автоматики за вердиктами пока нет:** оценки лежат в Phoenix, но никто не алёртит по доле `incorrect` и не блокирует промпт. Петля «оценка → решение → промоушен» замыкается в итерации 6 (Prefect), и то по golden-сету, а не по judge-оценкам.
- **Кассет у судьи нет и не будет:** харнесс `phoenix.evals` владеет своим вызовом (исключение tech-decisions), поэтому judge-шаги демо — live-only. Glue-логика вокруг (сэмплинг, skip, запись аннотаций) при этом полностью покрыта офлайн-тестами с фейками.
- **Порог «правильности» — один бинарный вердикт на весь триаж** (категория+приоритет+тон разом), без пооценочных полей и без оценки `draft_reply` как текста. Осознанный минимум: одна аннотация, один словарь меток.

## Карта «где в коде»

Номера строк — ориентир на момент итерации; имена функций надёжнее.

1. **Чистые решения судейства** — `app/domain/judge.py`: `JudgeCandidate` (:18), `JudgeVerdict` (:27), `sampled()` (:34), `select_for_judgement()` (:40). Домен без I/O решает две вещи: попадает ли тикет в выборку и кого из кандидатов ещё имеет смысл судить. Сэмплинг детерминированный — хеш от `ticket_id` укладывается в корзину `[0, 1)` и сравнивается с rate, поэтому один и тот же трафик всегда даёт одну и ту же выборку (это и делает свойство «повторный прогон = no-op» проверяемым).

    ```python
    def sampled(ticket_id: str, rate: float) -> bool:
        """Deterministic traffic sampling: same ticket -> same decision on every run."""
        bucket = int.from_bytes(hashlib.sha256(ticket_id.encode()).digest()[:8], "big") / 2**64
        return bucket < rate

    def select_for_judgement(candidates, *, judged_span_ids, rate):
        return [
            c for c in candidates if c.span_id not in judged_span_ids and sampled(c.ticket_id, rate)
        ]
    ```

2. **Шов span-стора** — `app/observability/phoenix.py`: константа `JUDGE_ANNOTATION` (:44) и четыре хелпера — `fetch_triage_spans()` (:47), `fetch_judge_annotations()` (:55), `extract_candidates()` (:70), `log_verdicts()` (:94). Весь «диалект» Phoenix-клиента (форма спан-словарей с точечными ключами, формат аннотации, потолок страницы `FETCH_LIMIT`) собран в одном модуле рядом со словарём спанов из 5a; workflow и оба отчёта зовут хелперы и деталей проводки не знают. `extract_candidates()` переводит сырые спаны в типизированные `JudgeCandidate` — так доменные функции никогда не видят стор-словари (симметрия с drift-сиблингом, где спаны тоже парсит скрипт, а не домен).

    ```python
    def log_verdicts(client: Client, verdicts: Iterable[JudgeVerdict]) -> None:
        """Write judge verdicts back as span annotations, next to the traces they judge."""
        payload: list[Any] = []
        for v in verdicts:
            # Phoenix's AnnotationResult wants keys absent, not null, when there's no value.
            result: dict[str, str | float] = {"label": v.label}
            ...
            payload.append(
                {"span_id": v.span_id, "name": JUDGE_ANNOTATION,
                 "annotator_kind": "LLM", "result": result}
            )
        client.spans.log_span_annotations(span_annotations=payload, sync=True)
    ```

3. **Харнесс судьи** — `app/observability/judge.py`: промпт-шаблон `_TEMPLATE` (:27), словарь меток `_CHOICES` (:25), `judge_candidates()` (:41). Единственное место, знающее про `phoenix.evals`, и оно импортируется лениво внутри функции — replay-пути, тесты и CI пакет не загружают (тест это проверяет механически). Модель судьи нигде не названа: она резолвится из `llm-tiers.yaml` через `JUDGE_TIER` тем же `resolve_model()`, что и у триажа; ключ и base_url приходят явно из `Settings`. `client="openai"` пиннит харнесс к голому OpenAI SDK, чтобы адаптер `phoenix.evals` не уехал в litellm мимо нашей дисциплины правила 5. Тело цикла защищено try/except: упавший кандидат (сеть, 429, непарсибельный вердикт) пропускается и остаётся неосуждённым на следующий прогон, а уже оплаченные вердикты доезжают до Phoenix.

    ```python
    llm = LLM(
        provider="openai",
        client="openai",
        model=resolve_model(settings.judge_tier, settings.tiers_path),
        **client_kwargs,   # api_key / base_url — явно из Settings
    )
    evaluator = create_classifier(
        name=JUDGE_ANNOTATION, prompt_template=_TEMPLATE, llm=llm, choices=_CHOICES
    )
    ```

4. **Workflow-glue** — `app/workflow/judge_flow.py`: `JudgeRunner` (:31), `JudgeRunReport` (:34), `judge_traffic()` (:41). Чистая оркестровка пяти шагов из схемы выше; Phoenix-клиент приходит аргументом с транспортного boundary (как реестр-хендл), а судья — инжектируемый callable `runner`, так что тесты гоняют весь поток с фейками, не трогая ни сеть, ни `phoenix.evals`.

    ```python
    def judge_traffic(client: Client, settings: Settings, runner: JudgeRunner) -> JudgeRunReport:
        spans, truncated = fetch_triage_spans(client, settings)
        judged_ids = {a["span_id"] for a in fetch_judge_annotations(client, settings, spans)}
        candidates = select_for_judgement(
            extract_candidates(spans), judged_span_ids=judged_ids, rate=settings.judge_sample_rate
        )
        verdicts = runner(candidates) if candidates else []
        if verdicts:
            log_verdicts(client, verdicts)
        ...
    ```

5. **Live-транспорт** — `app/cli/judge.py:22` (`main()`). Тонкий адаптер по образцу `batch`: проверяет, что ключ вообще есть (судья — живые деньги, правило 4), открывает Phoenix-клиент на boundary и передаёт в workflow лямбду поверх `judge_candidates`. Печатает вердикт с объяснением на каждый спан и итоговую строку вида `56 spans judged at tier=smart (84 traced, 0 already judged, sample_rate=0.5)`.

6. **Отчёт по стору** — `scripts/judge_report.py:24` (`main()`). Симметричен `drift_report`: читает спаны и аннотации `triage_quality` через те же хелперы шва, печатает JSON со счётчиками меток и повердиктным списком по тикетам. Exit-код механический: 0 = осуждённые спаны существуют (done-gate), 1 = судья ещё не запускался.

7. **Настройка сэмпла** — `app/config.py:51`: `judge_sample_rate: float = 0.5`. По конвенции «env только через `Settings`»: сменить долю судимого трафика = одна строка env (`JUDGE_SAMPLE_RATE=1.0` — судить всё).

8. **Пин харнесса** — `pyproject.toml:26`: `arize-phoenix-evals>=3.1,<4` (точная версия в `uv.lock`), с комментарием, что пакет live-гейтится и лениво импортируется.

9. **Make-цели** — `Makefile:78-84`: `make judge` (гейт на `.env`, комментарий с ценой) и `make judge-report`.

10. **Офлайн-тесты глушат живой путь** — `tests/test_judge.py`: детерминизм сэмпла, парсинг/отбор кандидатов, happy-path всего glue с фейковым клиентом и фейковым судьёй, идемпотентный повторный прогон (судья не вызывается, записей нет) и ассерт, что `phoenix.evals` не появился в `sys.modules`.
