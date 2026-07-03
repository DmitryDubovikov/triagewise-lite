# Итерация 02 — promptfoo: CI eval-gate

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.
> Новый инструмент один — **promptfoo**: champion-промпт гоняется по версионируемому golden-сету,
> и регрессия промпта делает CI красным. DVC (перенос из sentiment-mlops) версионирует сам golden-сет.

## Зачем это (продукт и ценность)

triagewise-lite сортирует входящие support-тикеты вымышленного SaaS *Driftwood*: по каждому тикету
модель определяет категорию, приоритет, тон, решает, нужен ли живой человек, и набрасывает черновик
ответа. Продукт при этом — не сам сортировщик, а операционный контроль над LLM-конвейером.

После iter 1 промпт стал версионируемым артефактом — но ничто не мешало влить в main правку промпта,
после которой триаж начинает отвечать прозой вместо структуры и весь конвейер тихо ломается. Именно
эту дыру закрывает текущая итерация: у конвейера появились **автоматические ворота против регрессий
промпта**. Теперь есть эталонная выборка из 40 размеченных тикетов (включая заведомо каверзные), и
каждый push/PR автоматически прогоняет рабочий промпт по ней; если после правки промпта выход перестал
соответствовать контракту — CI краснеет и мёрдж заблокирован. Саппорт-лид получает гарантию, что
«улучшение» промпта не доедет до прода, не пройдя через ворота, — вместо «поменяли промпт и молимся».

## 🧵 Что это дало резюме

Делает демонстрируемой north-star строку **«CI eval-gate / regression testing для LLM»** (ROADMAP,
строка 2). Доказательства-артефакты: golden-сет под **DVC** (`data/golden.jsonl.dvc` в git, сам файл
— в DVC-remote); job `eval-gate` в `.github/workflows/ci.yml`, гоняющий promptfoo без секретов и сети;
и **красная демка** в `specs/02/red-demo.log` — оба пути к красному прогнаны по-настоящему: изменение
промпта без перезаписи артефакта (miss-red, $0) и live-перезапись испорченного промпта, на которой
падают все 40 формат-ассертов (assert-red). Заодно закрыт кусочек зонтичного «LLMOps»: конвейер
`golden → build → record → replay` — это CD-дисциплина для промптов, а не разовый скрипт.

## TL;DR (простыми словами)

Было — промпт лежит в реестре версиями, но «не сломали ли его правкой» проверялось глазами. Стало —
есть эталон: 40 размеченных тикетов под DVC; promptfoo прогоняет champion-промпт по всем 40 и
проверяет каждый ответ на строгий формат (валидный JSON с пятью нужными полями и правильными
enum'ами); в GitHub Actions это отдельный job, который жжёт $0 и не требует ключа — ответы модели
записаны заранее в закоммиченный файл, и CI их только реплеит. Поменял промпт и не перезаписал
ответы — реплей промахивается, CI красный. Перезаписал, но промпт стал хуже и ломает формат — ассерты
красные. Оба пути к красному проверены живьём.

## Что это за инструмент

**promptfoo** — это тест-раннер для промптов, Node-CLI: как pytest, только тест-кейсы — это входы для
промпта, а проверки — ассерты на ответ модели. Ему описывают в YAML-конфиге три вещи: какие промпты
гонять, через какого провайдера и по каким тест-кейсам; он прогоняет матрицу «промпт × тесты» и
отдаёт pass/fail со сводкой. Здесь он — движок ворот в CI: гоняет наш champion-промпт по golden-сету
и валит job при нарушении контракта. Три понятия, которыми оперирует весь документ:

- **провайдер** — то, что отвечает на отрендеренный промпт. У promptfoo есть родной OpenAI-провайдер
  (им пишем ответы live), но провайдером может быть и свой python-файл — этим трюком мы реплеим
  записанные ответы офлайн.
- **тест-кейс** — один вход: переменные `{{subject}}`/`{{body}}`, подставляемые в промпт. Наши 40
  тест-кейсов сгенерированы из golden-тикетов.
- **ассерт** — проверка ответа. Мы используем единственный `is-json` со схемой: ответ обязан быть
  валидным JSON, соответствующим Pydantic-схеме `TriageResult` (5 обязательных полей, enum'ы
  priority/sentiment, boolean needs_human).

**DVC** здесь не новый инструмент (перенос из sentiment-mlops), поэтому коротко: это «git для данных»
— в git коммитится маленький `.dvc`-файл с md5-хэшем, а сам файл данных живёт в отдельном хранилище
(у нас — локальная папка `../triagewise-lite-dvc-remote` рядом с репо) и восстанавливается командой
`dvc pull`.

## Поток данных

Ворота живут в трёх процессах с разными триггерами: **build** (запускает разработчик, офлайн, $0),
**record** (запускает разработчик по явному go, live, деньги) и **replay** (запускает CI на каждый
push/PR, офлайн, $0). Разберём в порядке появления данных.

**Build: разработчик перегенерирует ассеты ворот.** Всё начинается с эталона — `data/golden.jsonl`,
40 размеченных тикетов (8 из них «джокеры»: двусмысленная категория, скрытый негатив под вежливой
формой, пограничные needs_human). Файл версионируется DVC и в git не лежит — а CI не умеет делать
`dvc pull` (remote локальный). Поэтому ворота в CI работают не по golden напрямую, а по производным
ассетам, которые генерятся из него локально и коммитятся. Когда golden или champion-шаблон меняется,
разработчик запускает `make eval-build`: команда через `app/workflow/eval_assets.py` читает golden,
берёт champion-шаблон из кода и модель из `llm-tiers.yaml` — и детерминированно рендерит три файла в
`eval/`: конфиг promptfoo (с `is-json`-ассертом из схемы `TriageResult`), 40 тест-кейсов и файл
промпта. Повторный прогон даёт те же байты, а в шапке каждого YAML стоит md5 golden-сета — тот же
хэш, что в `data/golden.jsonl.dvc`, так что рассинхрон источника и производных виден на глаз (и
ловится sync-тестом).

**Record: разработчик записывает эталонные ответы (⚠️ live, деньги).** Чтобы CI мог проверять ответы
модели, не звоня модели, ответы нужно записать заранее. По явному go разработчик запускает
`make eval-record`: promptfoo гоняет все 40 тестов через свой родной OpenAI-провайдер
(`gpt-4.1-nano`, снапшот запиннен — это единственное место, где ворота стоят денег, ≈$0.01), а затем
`scripts/extract_eval_outputs.py` дистиллирует результаты в `eval/outputs.json` — словарь
«хэш отрендеренного промпта → ответ модели», который коммитится в git.

**Replay: CI гоняет ворота на каждый push/PR ($0, без ключа).** GitHub Actions запускает `make eval`.
Это тот же promptfoo с тем же конфигом и теми же 40 тестами, но провайдер подменён флагом
`--providers file://replay_provider.py`: вместо сети ответы отдаёт наш python-файл, который хэширует
пришедший отрендеренный промпт и ищет ответ в `eval/outputs.json`. Нашёл — ответ идёт в
`is-json`-ассерт как ни в чём не бывало. Не нашёл (единственная причина — промпт изменился, а
перезаписи не было) — провайдер возвращает громкую ошибку. Финальный штрих — jq-пост-чек в Makefile:
promptfoo выходит с кодом 0, когда *абортит* прогон на ошибках провайдера, поэтому настоящие ворота —
проверка «ошибок ноль, падений ноль и прогнались все 40», иначе `exit 1` и job красный.

```
 BUILD (локально, $0)                       RECORD (локально, ⚠️ live ≈$0.01)
 ────────────────────                       ──────────────────────────────────
 data/golden.jsonl (DVC, не в git)          make eval-record
        │                                        │
        │ make eval-build                        ├─► promptfoo + родной OpenAI-провайдер
        ▼                                        │      (gpt-4.1-nano, 40 вызовов)
 scripts/build_eval.py                           ▼
   └─ app/workflow/eval_assets.py           eval/.record-results.json (gitignored)
        │                                        │
        ▼  (коммитятся)                          │ scripts/extract_eval_outputs.py
 eval/promptfooconfig.yaml                       ▼
 eval/tests.yaml            ┌──────────►  eval/outputs.json (коммитится)
 eval/prompts/champion.json │             {hash(промпт) → ответ модели}
                            │                    │
 REPLAY (CI, каждый push/PR, $0, без ключа)      │
 ──────────────────────────────────────────      │
 make eval                                       │
   └─► promptfoo --providers file://replay_provider.py
            │ hash(отрендеренный промпт) ────────┘
            ├─ hit  → ответ → is-json(схема TriageResult) → pass/fail
            └─ miss → [ERROR] "prompt changed?" → abort
                 │
                 ▼
   jq-пост-чек: successes==40 && errors==0 && failures==0 → зелёный, иначе exit 1
```

Два пути к красному CI — то, ради чего ворота существуют:

```
 промпт изменён,                промпт изменён и перезаписан,
 outputs.json не перезаписан    но стал хуже (ломает формат)
        │                              │
        ▼                              ▼
   реплей-MISS                    реплей-HIT, но ответ — проза
        │                              │
   provider error                 is-json ассерт падает
        └──────────┬───────────────────┘
                   ▼
        eval-gate КРАСНЫЙ → мёрдж заблокирован
```

| Инструмент / шаг | Что делает | Куда пишет |
|---|---|---|
| DVC (`dvc add/push/pull`) | версионирует `data/golden.jsonl`; в git — только `.dvc`-файл с md5 | локальный remote `../triagewise-lite-dvc-remote` |
| `make eval-build` → `scripts/build_eval.py` | рендерит promptfoo-ассеты из golden + champion-шаблона + тира, детерминированно | `eval/promptfooconfig.yaml`, `eval/tests.yaml`, `eval/prompts/champion.json` (в git) |
| `make eval-record` (⚠️ live) | promptfoo с родным OpenAI-провайдером гоняет 40 тестов | `eval/.record-results.json` (gitignored) |
| `scripts/extract_eval_outputs.py` | дистиллирует record-результаты в реплей-артефакт с ключами `hash(промпт)` | `eval/outputs.json` (в git) |
| `make eval` → promptfoo + `eval/replay_provider.py` | реплеит записанные ответы офлайн; miss = громкая ошибка | `eval/.results.json` (gitignored) |
| jq-пост-чек (Makefile, цель `eval`) | настоящие ворота: `successes==40 && errors==0 && failures==0`, иначе `exit 1` | только exit-код |
| `.github/workflows/ci.yml`, job `eval-gate` | запускает `make eval` на каждый push/PR, без секретов | статус чека на PR |

Чего в этой итерации **НЕ** происходит (типичная путаница). Ассерты проверяют **только формат/поля**
— разметка golden (правильная категория, приоритет и т.д.) лежит в `eval/tests.yaml` метаданными для
человека, но ни один ассерт по ней не судит: accuracy — не ворота (правило 1), label-гейт и сравнение
champion-vs-challenger — территория iter 6. promptfoo в CI **не звонит модели вообще** — ни ключа, ни
сети, ни секретов в workflow нет. Стоимость/латентность здесь не считаются (iter 3), дрейф не ловится
(iter 5). И промпт не улучшался — champion тот же, что в iter 1.

## Карта «где в коде»

> Номера строк — ориентир на момент итерации 2; опирайся на имена символов, они переживают дрейф строк.

1. **Схемы golden-тикета** — `app/domain/triage.py:32` (`GoldenLabels`) и `:42` (`GoldenTicket`).
   Golden-тикет — это обычный `Ticket` плюс разметка `expected` и опциональная пометка `joker` для
   каверзных случаев. Разметка — это `TriageResult` минус `draft_reply` (у свободного текста нет
   эталонного ответа). Важно: это метаданные фикстуры, а не новые выходные поля триажа — правило 3
   (замороженный выход) не тронуто.
   ```python
   class GoldenLabels(BaseModel):
       category: str
       priority: Priority
       sentiment: Sentiment
       needs_human: bool

   class GoldenTicket(Ticket):
       expected: GoldenLabels
       joker: str | None = None
   ```

2. **Чтение golden-сета** — `app/persistence/tickets.py:16`, `load_golden()`. Устроена как сосед
   `load_tickets()`: читает JSONL и валидирует каждую строку через Pydantic. Валидация — и есть
   смысл функции: криво размеченная строка (не тот enum, пропущенное поле) падает здесь, громко и
   с адресом, а не молча уезжает дальше в ворота.
   ```python
   def load_golden(path: Path) -> list[GoldenTicket]:
       lines = path.read_text().splitlines()
       return [GoldenTicket.model_validate(json.loads(line)) for line in lines if line.strip()]
   ```

3. **Рецепт генерации ассетов (сердце build-пути)** — `app/workflow/eval_assets.py:53`,
   `build_assets()`, и `:90`, `build_from_settings()`. Первая — чистый рендер: получает golden, md5
   и модель, возвращает словарь «относительный путь → содержимое файла» для трёх ассетов. Ассерт
   ворот она берёт не из рукописного YAML, а прямо из домена — `TriageResult.model_json_schema()`
   становится значением `is-json`: контракт выхода один, и он живёт в Pydantic-схеме. Вторая
   функция — единый рецепт «прочитай golden, разрезолвь тир, отрендери», который делят build-скрипт
   и sync-тесты: если у рецепта появится новый вход, он появится у обоих.
   ```python
   config = {
       "description": "Driftwood triage — CI eval gate (format/fields only)",
       "prompts": [f"file://{PROMPT_FILE}"],
       "providers": [{"id": f"openai:chat:{model}", "config": {"temperature": 0}}],
       "defaultTest": {
           "assert": [{"type": "is-json", "value": TriageResult.model_json_schema()}]
       },
       "tests": f"file://{TESTS_FILE}",
   }
   ```
   Модель приходит из `llm-tiers.yaml` через `resolve_model(settings.triage_tier, …)` — promptfoo
   владеет своим вызовом (санкционированное исключение из `route()`, tech-decisions), но пин-гейт
   датированных снапшотов держится и здесь: в конфиг попадает `openai:chat:gpt-4.1-nano-2025-04-14`.

4. **Build-скрипт** — `scripts/build_eval.py:15`, `main()`. Тонкий адаптер над рецептом: берёт
   ассеты у `build_from_settings()` и раскладывает по `eval/`. Печатает, что записал, — идемпотентно,
   офлайн, $0.

5. **Файл-реплей-провайдер (сердце replay-пути)** — `eval/replay_provider.py:34`, `prompt_key()`, и
   `:43`, `call_api()`. Это python-провайдер promptfoo: на каждый тест promptfoo зовёт `call_api()`
   с отрендеренным промптом, а тот хэширует промпт и ищет запись в `eval/outputs.json`. Ключевое
   свойство: ключ — это хэш **всего отрендеренного промпта**, поэтому любая правка шаблона
   инвалидирует все 40 записей разом — устаревшие ответы физически не могут держать CI зелёным.
   Промах отвечает не пустотой, а ошибкой, которая сама говорит, как себя починить. Файл нарочно
   stdlib-only: promptfoo запускает его системным `python3`, вне uv-окружения, поэтому импортировать
   `app/*` ему нельзя.
   ```python
   def prompt_key(prompt: str) -> str:
       """Hash the rendered prompt, whitespace-insensitively (chat prompts render as JSON)."""
       try:
           canon = json.dumps(json.loads(prompt), sort_keys=True, separators=(",", ":"))
       except ValueError:
           canon = prompt
       return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]

   def call_api(prompt, options, context):
       ...
       entry = recorded.get(prompt_key(prompt))
       if entry is None:
           return {"error": f"no recorded output (key {key}) — prompt changed? {RECORD_HINT}"}
       return {"output": entry["output"]}
   ```

6. **Экстрактор реплей-артефакта** — `scripts/extract_eval_outputs.py:19`, `main()`. Вторая половина
   `make eval-record`: читает сырые результаты live-прогона и дистиллирует их в `eval/outputs.json`.
   Ключи он считает **той же** функцией `prompt_key` из реплей-провайдера (модуль импортируется по
   пути через `load_replay_provider()`), причём хэширует ровно ту строку, которую провайдер получит
   при реплее, — запись и реплей не могут разъехаться по определению. Если у какого-то теста в
   live-прогоне нет ответа, скрипт отказывается писать частичный артефакт.
   ```python
   key = provider.prompt_key(r["prompt"]["raw"])
   outputs[key] = {"id": description.split(":")[0], "output": output}
   ...
   doc = {"_generated": "...", "model": results[0]["provider"]["id"],
          "outputs": dict(sorted(outputs.items()))}
   ```

7. **Make-цели ворот** — `Makefile:24` (`eval-build`), `:31` (`eval`), `:45` (`eval-record`).
   Цель `eval` — это и есть ворота: promptfoo с провайдер-оверрайдом плюс jq-пост-чек. Пост-чек
   существует, потому что promptfoo выходит с кодом 0, когда абортит прогон на ошибках провайдера, —
   без него miss-red был бы «зелёным». Красный он не только при ошибках/падениях, но и если
   прогналось меньше тестов, чем записей в артефакте.
   ```make
   eval:
   	$(PROMPTFOO_ENV) PROMPTFOO_CACHE_ENABLED=false PROMPTFOO_PYTHON=python3 \
   		npx promptfoo eval -c eval/promptfooconfig.yaml \
   		--providers file://replay_provider.py \
   		--no-progress-bar --output eval/.results.json
   	jq -e --argjson n "$$(jq '.outputs | length' eval/outputs.json)" \
   		'.results.stats | .failures == 0 and .errors == 0 and .successes == $$n' \
   		eval/.results.json >/dev/null \
   		|| { echo "eval gate RED: failures/errors present or not every test ran"; exit 1; }
   ```
   `eval-record` дополнительно требует `.env` с ключом и включает локальный кэш promptfoo
   (gitignored) — повторная перезапись неизменившихся промптов бесплатна.

8. **CI-workflow** — `.github/workflows/ci.yml:14` (job `check`) и `:25` (job `eval-gate`). Два
   независимых гейта: классический статический (`make check` через uv) и LLM-регрессионный. Job
   `eval-gate` ставит Node 22, восстанавливает `node_modules` из кэша по хэшу `package-lock.json`
   (иначе `npm ci`) и запускает `make eval` — секретов в job нет вообще, живой прогон в CI невозможен
   по построению (правило 4).
   ```yaml
   eval-gate:
     runs-on: ubuntu-latest
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-node@v4
         with: {node-version: "22", cache: npm}
       ...
       - run: make eval
   ```

9. **Тесты-стражи** — `tests/test_eval_assets.py` и `tests/test_replay_provider.py`. Разделены по
   признаку «нужен ли golden-сет». Первый файл требует golden (в CI его нет — `dvc pull` там не
   работает), поэтому целиком под `skipif`: локально он держит форму golden (ровно 40 тикетов, 8
   джокеров) и байтовую синхронность закоммиченных ассетов с источником. Второй файл golden не
   требует и **обязан** гоняться в CI: свойства реплей-провайдера (стабильные ключи, громкий
   промах) и два стража консистентности закоммиченного — записанная модель совпадает с
   провайдером в конфиге (иначе bump тира остался бы зелёным на ответах старой модели), а
   закоммиченный файл промпта совпадает с champion-шаблоном в коде.
   ```python
   def test_recorded_model_matches_configured_provider() -> None:
       config = yaml.safe_load((DEFAULTS.eval_dir / "promptfooconfig.yaml").read_text())
       recorded = json.loads((DEFAULTS.eval_dir / "outputs.json").read_text())["model"]
       assert recorded == config["providers"][0]["id"], (...)
   ```
   Оба файла читают пути из `Settings.model_construct()` — чистых дефолтов полей, без `.env` и
   env-переменных: транзиентный `TRIAGE_TIER` в шелле не должен ни уронить, ни молча перенацелить
   проверку закоммиченных файлов.

10. **DVC-обвязка и пин promptfoo** — `data/golden.jsonl.dvc`, `.dvc/config`, `package.json`.
    В git лежит только `.dvc`-указатель (md5 `7b60e7cd…`, тот же, что в шапках генерённых YAML);
    remote — локальная папка `../triagewise-lite-dvc-remote` (относительно `.dvc/` — соседка репо);
    аналитика DVC выключена. promptfoo запиннен точно (`"promptfoo": "0.121.17"` +
    `package-lock.json`, `node_modules` в .gitignore) — ворота не должны дрейфовать под нами.
