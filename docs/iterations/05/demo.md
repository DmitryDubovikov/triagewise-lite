# Демо итерации 05 (5a) — дрейф виден в Phoenix и ловится отчётом

Этот прогон доказывает практику **LLM output drift / quality monitoring**: продакшен-трафик триажа оставляет трейсы в observability-сервисе, и когда после «релиза фичи» в потоке появляется новая тема, система замечает это сама — по данным, а не по жалобам клиентов. Проверяем весь контур: Phoenix поднят → трафик двух пачек трейсится → отчёт по стору Phoenix механически выносит вердикт «дрейф есть». Всё демо офлайн и бесплатно: LLM-ответы читаются из кассет (`LLM_MODE=replay` — дефолт), live-шагов в этой итерации нет вообще.

Все команды выполняются из корня репо `/Users/dd/projects/pet/triagewise-lite`.

### 1. Поднять control plane — MLflow и Phoenix

Без Phoenix спанам некуда лететь, без MLflow триажу неоткуда взять промпт.

```bash
make up
docker compose ps --format '{{.Name}} {{.Status}}'
```

**Ожидаемо:** оба контейнера в статусе `Up …`:

```
triagewise-lite-mlflow-1 Up ...
triagewise-lite-phoenix-1 Up ...
```

### 2. Убедиться, что промпт в реестре (идемпотентно)

Триаж грузит промпт по alias `champion` из MLflow — если реестр пустой (свежий volume), команда его наполнит; если промпт уже там, она ничего не пересоздаст.

```bash
uv run python -m scripts.register_prompt
```

**Ожидаемо:** в выводе для `champion` и `challenger` строки вида `prompts:/triage@champion -> v1  (unchanged, alias confirmed)` / `...@challenger -> v2  (unchanged, alias confirmed)` (на свежем сторе — `registered`), без роста номеров версий при повторном запуске.

### 3. Кассеты обеих пачек на месте, оплаченная запись защищена

Кассеты закоммичены, так что этот шаг — no-op-проверка идемпотентности автора: повторный запуск перезаписывает фабрикации в те же файлы, а единственную **живую** (оплаченную) кассету DW-001 не трогает.

```bash
uv run python -m scripts.author_cassette --all 2>&1 | grep -E "Skipping|DW-101" 
```

**Ожидаемо:** первая строка — защита оплаченной записи, дальше обычный авторинг:

```
Skipping DW-001: live-recorded cassette exists (a634df347266…) — a fabrication never clobbers a paid recording
Wrote cassette for DW-101 (cheap -> gpt-4.1-nano-2025-04-14): 4a2cbbd139a0….json
```

### 4. Прогнать оба батча трафика с трейсингом — это и есть «online»-часть

Базовая пачка изображает обычный трафик, пострелизная — трафик после релиза Automations; обе — синтетические фикстуры в роли клиентского потока (golden-сет сюда не входит: он эталон CI eval-gate из итерации 2 и в мониторинге трафика не участвует). Каждый тикет уходит в Phoenix спаном с меткой пачки.

```bash
make traffic
```

**Ожидаемо:** по строке `[DW-…] категория` на каждый из 11 + 10 тикетов и по итоговой строке на пачку; в пострелизном выводе доминирует `automation`:

```
[DW-001] Login Issues
...
11 tickets triaged (batch=base, mode=replay, traced=True)
[DW-101] automation
...
10 tickets triaged (batch=postrelease, mode=replay, traced=True)
```

(`Login Issues` у DW-001 — не опечатка: это единственный тикет с **живой** записанной кассетой, и реальная модель назвала категорию в свободной форме; остальные ответы — сфабрикованные фикстуры со словарём golden-сета. Заодно это мини-иллюстрация того, что на живом трафике свободный словарь категорий шумит — почему наивный детектор новизны это переживает и как дыру закрывают по-взрослому, см. learnings.)

`traced=True` — признак, что спаны реально экспортировались (при выключенном Phoenix было бы `PHOENIX_ENABLED=0 — running untraced`).

### 5. Вердикт о дрейфе — из стора Phoenix, не из UI

Ключевой шаг: отчёт спрашивает сам Phoenix (REST-клиентом), агрегирует категории по пачкам и выносит механический вердикт exit-кодом. Это правило 8 в действии — верим стору, не глазам. Отчёт read-only и запускается по требованию: на триаж он не влияет, расписание для мониторинга появится только как практика итерации 6 (Prefect).

```bash
make drift-report; echo "exit=$?"
```

**Ожидаемо:** JSON с распределениями обеих пачек, `"new_categories": ["automation"]`, `"drifted": true`, финальная строка и нулевой exit-код:

```json
{
  "distributions": {
    "base": {"account_access": 1, "billing": 2, "bug": 4, "feature_request": 2, "how_to": 1, "Login Issues": 1},
    "postrelease": {"automation": 8, "account_access": 1, "billing": 1}
  },
  "new_categories": ["automation"],
  "drifted": true
}
```

```
DRIFT: new categories in 'postrelease': automation
exit=0
```

(Счётчики в `distributions` растут с каждым повторным `make traffic` — вердикт от этого не зависит, см. шаг 7.)

### 6. Посмотреть трейсы глазами (вспомогательная проверка, не основной путь)

Стор уже подтвердил дрейф на шаге 5; UI — просто витрина тех же данных для скриншота в отчёт.

Открыть http://localhost:6006 → проект `triagewise` → Traces.

**Ожидаемо:** спаны `triage_ticket` обеих пачек; у каждого в атрибутах `triage.batch`, `triage.category`, вход тикета и JSON-ответ триажа.

### 7. Идемпотентность: повторный трафик не ломает вердикт

Спаны append-only — повторный прогон добавит ещё 21 спан. Вердикт обязан не измениться, потому что отчёт сравнивает *распределения по пачкам*, а не абсолютные счётчики.

```bash
make traffic >/dev/null 2>&1 && make drift-report | tail -1; echo "exit=$?"
```

**Ожидаемо:**

```
DRIFT: new categories in 'postrelease': automation
exit=0
```
