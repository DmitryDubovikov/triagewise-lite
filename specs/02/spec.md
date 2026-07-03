# Итерация 02 — promptfoo: CI eval-gate

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Ввести **promptfoo** как ворота в CI: champion-промпт гоняется по версионируемому golden-сету, ассерты проверяют **формат/поля** замороженного выхода триажа; регрессия промпта делает CI красным и блокирует мёрдж. DVC (перенос из sentiment) версионирует golden-сет.

## 🧵 Красная нить (резюме)
ROADMAP, строка 2: **«CI eval-gate / regression testing для LLM»** — golden-сет под **DVC**; promptfoo гоняет champion-промпт по golden, ассертит формат/поля; **CI job красный при регрессии** (промпт «во вред» → мёрдж заблокирован).

## Новые инструменты (и минимальный объём каждого)
- **promptfoo** — Node-CLI, проектно-локально (`package.json`, версия запиннена). Минимум: один конфиг, один промпт (champion), ~40 тестов из golden, один `is-json`-ассерт со схемой `TriageResult` через `defaultTest`. Провайдер — свой OpenAI (`cheap`-тир из `llm-tiers.yaml`, снапшот запиннен); promptfoo владеет вызовами (исключение из `route()`, tech-decisions) → live гейтится.
- *(DVC — перенос из sentiment, не «новый инструмент»: init + add + локальный dir-remote вне репо + push.)*

## Решённые развилки (обсуждены)
- **CI = $0 через файл-реплей** (пересмотр по факту: первоначальный план «закоммиченный promptfoo-кэш» нереализуем — promptfoo хэширует в кэш-ключ весь запрос **включая API-ключ**, без настоящего ключа CI в кэш не попадает). Итог: запись — родной OpenAI-провайдер promptfoo live (гейтится, ≈$0.01) → `scripts/extract_eval_outputs.py` дистиллирует выходы в **закоммиченный `eval/outputs.json`** (ключ = хэш отрендеренного промпта); CI реплеит его через `eval/replay_provider.py` (python-провайдер promptfoo, stdlib-only, `--providers`-override). Смена промпта инвалидирует все ключи → miss = error = красный, пока не перезапишешь локально. Live-вызовами по-прежнему владеет promptfoo (развилка tech-decisions цела).
- **Ассерты — только формат/поля** (5 полей, enum'ы priority/sentiment, boolean needs_human). Метки golden кладём сейчас, но ими не судим (accuracy — не ворота; label-гейт — территория iter 6).
- **Golden: ~40 тикетов, 6 категорий** (account_access, billing, bug, feature_request, how_to, performance), ~8 джокеров (3 двусмысленная категория, 3 скрытый negative, 2 edge needs_human). Разметка: category/priority/sentiment/needs_human; draft_reply не размечаем.
- **Golden не в git** (DVC) → CI работает по **закоммиченным производным ассетам**, сгенерированным из golden локально. Риск рассинхрона принят (golden почти статичен) + локальный sync-тест (skip, если golden отсутствует — как в CI).

## Done-gate (по факту существования)
- `data/golden.jsonl` (~40 размеченных тикетов с джокерами) под DVC: `.dvc`-файл в git, локальный dir-remote настроен, `dvc push` прошёл, `dvc pull` возвращает файл.
- `scripts/build_eval.py` генерит promptfoo-ассеты (config + champion-промпт из `TRIAGE_CHAMPION_TEMPLATE` + тесты из golden; модель — из `llm-tiers.yaml`), **идемпотентно** (повторный прогон = те же байты). Ассеты закоммичены.
- `make eval` — promptfoo офлайн по закоммиченному `eval/outputs.json` через файл-реплей-провайдер, зелёный, $0, без ключа; jq-пост-чек — настоящие ворота (promptfoo выходит с 0 при abort'е на ошибках провайдера). Запись артефакта (`make eval-record`) — live по явному go.
- `.github/workflows/ci.yml`: job `check` (make check) + job `eval-gate` (npm ci + promptfoo eval по outputs.json, без секретов). Регрессия проверена локально обоими путями: miss-red ($0: промпт изменён, реплей промахивается) и assert-red (live-перезапись испорченного промпта → format-ассерты падают) — evidence в `specs/02/red-demo.log`; красное CI-демо — артефакт close.
- Ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. Deps: `dvc` в dev-deps (uv), `package.json` + `promptfoo` (pin + `package-lock.json`, `node_modules` в .gitignore).
2. Golden-сет: сгенерить и разметить `data/golden.jsonl`; `dvc init` + `add` + dir-remote + `push`.
3. `scripts/build_eval.py` → `eval/` (config, промпт, тесты; схема-ассерт); `Settings` — пути; sync/идемпотентность-тесты (skip без golden).
4. Makefile (`eval-build`, `eval`, `eval-record` с пометкой «деньги») + `.github/workflows/ci.yml`; live-запись кэша по явному go (~$0.01–0.02, включая красную демо-запись).
5. Ревью-пайплайн (general + constitution → auditor → фиксы) → `/simplify`.

## Вне scope
Label/accuracy-ассерты и сравнение champion-vs-challenger (iter 6) · S3/облачный DVC-remote (`# dl-lite`) · promptfoo как исследовательский eval (правило 7) · cost/latency (iter 3) · Phoenix (iter 5) · новые поля выхода · дрейф-пачка тикетов (iter 5).
