# Итерация 06 (6a) — промоушен-петля вручную: eval → gate → swap → hot-reload

> 🎯 Знакомство с инструментом минимальными затратами. Existence-gate, не accuracy-gate.

## Цель
Замкнуть champion/challenger-машинерию итерации 1 в работающий промоушен: challenger
re-eval'ится на golden-сете в `replay` ($0), gate решает «побил ли champion», alias
`champion` переезжает в реестре, а живой access-layer подхватывает новую версию без
рестарта. Нового инструмента нет — итерация замыкает уже стоящие (Prefect-обёртка — 6b).

## 🧵 Красная нить (резюме)
> **Champion/challenger промоушен промптов — замыкание (CD для промптов): eval → gate → swap → hot-reload** (ROADMAP, строка 6a; двигает north-star пункт 2 «Prompt-as-artifact + champion/challenger промоушен промптов»).

## Новые инструменты (и минимальный объём каждого)
- нет (правило 2 не тратится). Всё — композиция iter 1 (реестр/alias) + iter 0 (route/кассеты) + golden iter 2.

## Done-gate (по факту существования)
`make promote` в `replay` ($0, офлайн): печатает score champion vs challenger по golden,
gate срабатывает (challenger > champion), **swap** — и verify **в самом реестре** (правило 8):
alias `champion` указывает на версию challenger-шаблона. **Hot-reload**: тест в `replay` —
один процесс, один registry-хендл: triage до swap идёт champion-шаблоном, после swap —
challenger-шаблоном, без переоткрытия клиента.
**Идемпотентность:** повторный `make promote` = no-op (challenger не «>» самого себя):
alias не дрейфует, версии не плодятся; `sync_prompts` после промоушена **не откатывает**
alias `champion` (владение alias переходит петле, sync только сеет недостающее).
+ ревью-пайплайн чист (CRITICAL/BUG = 0).

## Шаги
1. **Derived-кассеты ($0):** скрипт фабрикует ответы golden-тикетов из их `expected`-меток —
   challenger отвечает верно, champion ошибается на джокерах (детерминированное правило) —
   и пишет кассеты через тот же `cassette_key` для **обоих** шаблонов; фикстурные тикеты
   (`replies.jsonl`) дополнительно получают кассеты под challenger-шаблон, чтобы triage-трафик
   replay'ился и **после** промоушена. Пометить `# dl-lite: фабрикация → апгрейд = live record`.
2. **Domain (чисто):** `score_triage(result, expected)` — доля совпавших label-полей
   (category/priority/sentiment/needs_human; draft_reply вне сравнения) и gate-решение
   `challenger_score > champion_score` (строго).
3. **Workflow + persistence:** promotion-флоу (registry-хендл аргументом с boundary):
   re-eval обоих alias'ов на golden через `route()` → gate → swap alias в persistence;
   `load_triage_prompt` становится alias-fresh (без стейл-кэша по URI — иначе hot-reload
   не работает); `sync_prompts` перестаёт владеть alias `champion` (сеет только недостающее,
   не двигает существующий — промоушен не откатывается).
4. **Transport:** `app/cli/promote.py` + `make promote` — печатает scores, решение gate,
   alias до/после и verify из стора. Тесты в `replay`: happy-path промоушена, идемпотентный
   повтор, hot-reload.
5. Ревью-пайплайн (general + constitution → аудитор → фиксы → `/simplify`).

## Вне scope
Prefect / расписание (6b) · live re-eval (promptfoo и record — деньги; петля демонстрируется
на derived-кассетах) · промоушен пары промпт×тир · новые поля триажа · UI поверх петли ·
метрики качества сверх label-match (existence-gate).
