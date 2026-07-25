# PLAN.md — Глобальный архитектурный план Neyra-AIAssist

## 1) Стратегическая цель

Построить модульную, event-driven и локально-автономную AI-платформу, где:

- ядро (`core`) стабильно работает как оркестратор,
- интерфейсы реализованы как плагины,
- Web UI управляет системой в real-time через события,
- память управляется как полноценный lifecycle (а не просто накопление),
- интеграции масштабируются через MCP (Model Context Protocol), без разрастания самописных адаптеров в ядре.

---

## 2) Базовые архитектурные принципы

- **Event-first:** межмодульное взаимодействие только через Event Bus контракты.
- **Plugin-first:** интерфейсная логика живет в `interfaces/`, ядро остаётся универсальным.
- **Secure-by-boundary:** `core` защищен от прямой саморедактируемости; расширения делаются через sandbox в плагинной зоне.
- **Local-first runtime:** облачные API опциональны; целевой режим — **свой сервер** (домашний ПК / NAS / VPS) с локальными или кастомными моделями. Устройства (колонка, телефон) — тонкие клиенты, не полный стек Neyra внутри колонки.
- **MCP-native future:** внешние возможности подключаются стандартизированными MCP-серверами.

### Двухполушарная когнитивная схема (OpenRouter)

Роли моделей в `openrouter.*` разделены по «полушариям» и подсистемам:

| Роль | Модель (целевой id) | Назначение |
|------|---------------------|------------|
| **Левое полушарие** (`brain_model.model`) | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Быстрый мультимодальный сенсор-маршрутизатор: tool-loop, нативный ввод изображений при `use_brain_model_for_vision: true`. |
| **Правое полушарие** (`brain_model.model_deep`) | `openai/gpt-oss-120b:free` | Глубокая аналитика, сложная логика, программирование — через инструмент `delegate_to_deep_logic`. |
| **Гиппокамп** (`memory_model`) | `openrouter/owl-alpha` | Консолидация LTM, Working Memory, рефлексии, эмоциональный слой; без жёсткого `max_tokens` в конфиге (нативный лимит провайдера). |
| **Talk** (`talk_model`) | без изменений (напр. Qwen3 235B) | Финальный ответ пользователю. |

**Зрение:** при `openrouter.vision_model.use_brain_model_for_vision: true` изображения идут в Nemotron (brain) в мультимодальном формате OpenRouter; при `false` — классический VL-caption через `vision_model` (fallback-парсеры сохранены).

**Rate limit:** вызовы `memory_model` обёрнуты в retry с экспоненциальной задержкой (HTTP 429 / таймаут), чтобы ночная консолидация и WM не роняли ядро.

---

## 3) Текущее состояние (сводно)

*Раздел намеренно очищен — обновить после cutover Memory Hub v2 / раскладки `core/`.*

---

## 4) Очередь этапов

Этап **1** — фундамент памяти и реорганизация ядра (база Neyra); этапы **2–4** — дальше по очереди.

**Порядок реализации:**

1. **Этап 1** — Memory Hub v2 (SQLite + семантическая Chroma) и рефакторинг `core/`.
2. **Этап 2** — Дополнительные точечные улучшения (персона, pre-context, безопасность, архив сессии).
3. **Этап 3** — Web UI как WebSocket-мост к Event Bus (тонкий клиент; тестируется без колонки).
4. **Этап 4** — Автономный сервер + тонкие клиенты / колонка (дальнее будущее: self-host моделей + переключаемый voice; физическую колонку пока нечем стабильно гонять).

---

## Этап 1 — Memory Hub v2 + реорганизация ядра `core/`

**Цель:** пересобрать базу памяти и структуру ядра: один Memory API, SQLite как source of truth для основного контента, Chroma только как семантический индекс «что вспомнить», полный chat log в БД; затем — чистка дублей и раскладка `core/` по папкам. Фундамент должен быть жёстким: без полуlegacy-путей и без «файлов-призраков» рядом с Hub.

**Статус:** **1A** и **1B** приняты в `main` ([PR #1](https://github.com/KORESHon/Neyra-AIAssist/pull/1), [PR #6](https://github.com/KORESHon/Neyra-AIAssist/pull/6) merged `1d61ed5`). Дальше — фаза **1R** (глубокий рефакторинг / split монолитов / раскладка остатков `core/`).

### Прогресс фазы 1A (факт в main)

Легенда: `[x]` = сделано в main; `[~]` = частично; `[ ]` = не сделано.

**В main (кратко):** пакет `core/memory/` (SQLite Hub, chat_log, semantic adapter), Hub-only чтение/запись people/diary/journal/WM (cutover-флаги `hub_legacy_import/fallback/dual_write` удалены из кода и конфига), `recall_chat` + API с фильтрами, `rag_write_mode`, prompt inject через Hub, backup `.db`, **legacy-импорт полностью упразднён** (`core/memory/legacy_import.py`, `run_hub_legacy_import()`, `POST /v1/memory/import-legacy`, marker-gated авто-импорт — удалены целиком, не просто выключены), ADR-0001, smoke `scripts/test_memory_hub_smoke.py` + `scripts/test_memory_cutover_offline.py`, dashboard/MCP Hub stats, people identity lookup через SQLite (cutover-safe), reflection diary/chat/journal Hub read-path (включая фикс `_hydrate_journal_from_hub`: `newest_first=True` + reverse в RAM, чтобы не терять свежие записи), **хостовая TZ** (`core/timeutil.py`, `system.timezone` optional).

**Процесс ревью:** Cursor Automation **Auto Review Neyra** (comment-only на push в PR). Перед коммитом — смотреть комменты бота при наличии.

#### Закрытие 1A

| # | Задача | Статус |
|---|--------|--------|
| 1 | People/diary/journal/WM: dual-write ещё включён по умолчанию; истина должна стать **только SQLite** | `[x]` Hub — единственный стор при подключении, без флагов |
| 2 | Cutover flags: `hub_legacy_import/fallback/dual_write` → `false` на стенде после импорта | `[x]` **флаги и весь legacy-импорт удалены из кода и конфига полностью** (не просто `false`/выключены); JSON-данных для миграции не было — авто-импорт и ручной `run_hub_legacy_import`/`/v1/memory/import-legacy` убраны как класс, а не оставлены safety-net'ом |
| 3 | **Удалить** file PeopleDB/Diary/journal/WM dual-write как реальный стор при подключённом Hub | `[x]` при `agent.memory_hub`/`self.memory_hub` — только SQLite; `PeopleDB`/`NeyraDiary` вообще не трогают файловую систему (ни чтение, ни запись) даже без Hub — только in-memory кэш; тонкие read/write-обёртки (`PeopleDB`, `NeyraDiary`, `ReflectionEngine`, WM refresh) сохранены; `_hub_dual_write`/`hub_legacy_fallback` убраны из reflection/hub; diary recursion (`NeyraDiary.recent_text` ↔ `hub.diary_recent_text`) исправлена; smoke обновлены |
| 4 | Полный e2e на стенде: chat → Hub chat_log → `/v1/memory/*` / healthcheck | `[x]` live 2026-07-24 MCP |
| 5 | Merge PR #1 в `main` после зелёного cutover | `[x]` merged 2026-07-24 (`8e04644`) |

**API cutover-safe:** `GET /v1/memory/people/{id}` резолвит id/имя → legacy-shape + summary/facts по каноническому `person_id` (как list).

**Не блокирует 1A:** Fast-Path умного дома → этап 2. Фаза **1B** (раскладка `core/`) — следующий шаг.

---

### Фазы внутри этапа (обязательный порядок)

Не смешивать миграцию памяти с большой раскладкой папок.

| Фаза | Фокус | Done when |
|------|--------|-----------|
| **1A — Memory Hub** | SQLite + Hub + chat log + перенос слоёв + Chroma semantic + API/tools/events/debug | Агент и `/v1/memory/*` живут только через Hub; legacy primary store выключен |
| **1B — Core layout** | Пакеты `plugins` / `llm` / `runtime` / `voice` / `memory.stores` + shims + lazy imports | `compileall` + memory smokes + healthcheck + Auto Review; без смены поведения |
| **1R — Core refactor** | Split монолитов (`agent.py` и др.), логические имена файлов, аудит костылей/багов, финальная раскладка по подпапкам `core/` | Код читаем по полкам; shims сняты или сужены; smokes/healthcheck/Discord без регрессий |

Правило: **1A → 1B → 1R**. Не смешивать миграцию памяти с большой раскладкой; не смешивать package-move (1B) с глубоким рефакторингом логики (1R).

---

### Целевая модель памяти

| Роль | Что хранит | Где |
|------|------------|-----|
| **Истина диалога** | полный chat log (кто / что / когда / где / ответ / эмоции / meta) | SQLite |
| **Истина о людях / журнале / дневнике / WM** | структурированные сущности | SQLite |
| **Индекс воспоминаний** | knowledge, digests, важные факты, diary/journal summaries — для RAG | Chroma (`type` в metadata) |
| **Кэш сессии** | STM (короткое окно) | RAM и/или view «последние N» из chat log |
| **Персона** | характер / system prompt | `config` / файлы промпта — **не** в памяти диалогов |

Правило записи: **не** класть сырой каждый ход целиком в Chroma. Полный ход → SQLite `chat_log`; в Chroma — только то, что имеет смысл вспоминать по смыслу.

**Инжект в промпт (talk/brain):** только через Hub (никаких прямых чтений jsonl / PeopleDB / md). Порядок секций сохранить близко к текущему (активный собеседник → упомянутые → WM → semantic RAG → brain summary → diary → web/tools/vision) или упростить осознанно в том же PR с комментарием в ADR — не «разъехаться молча».

---

### Конфиг (`config.example.yaml` + локальный `config.yaml`)

Зафиксировать ключи (имена уточняемы, смысл — обязателен):

| Ключ (ориентир) | Назначение |
|-----------------|------------|
| `memory.sqlite_path` | путь к БД, default `./memory/neyra_memory.db` |
| `memory.chroma_db_path` | семантический индекс (как сейчас) |
| `memory.rag_enabled` | вкл/выкл semantic search |
| `memory.rag_top_k` | top-k Chroma |
| `memory.rag_write_mode` | `off` \| `digest` \| `important_only` (запрет legacy «каждый dialog raw») |
| `memory.chat_log_retention_days` | опц. TTL/prune лога (0 = без автоудаления) |
| `memory.stm_max_messages` | размер STM-окна |
| `memory.working_memory.*` / `emotional_layer.*` / prune-summarize | перевести на Hub, не на файлы |

Cutover-флаги (`hub_legacy_import`, `hub_legacy_fallback`, `hub_dual_write_legacy`) **удалены** из кода и конфига — Hub SQLite всегда единственный стор при подключении. Legacy-импорт (`run_hub_legacy_import()`, `POST /v1/memory/import-legacy`, marker-gated авто-импорт) **полностью упразднён** — не осталось ни ручного, ни автоматического пути импорта json/jsonl/md; мигрировать было нечего.

Документировать в ADR + example; синхронизировать корневой `config.yaml` по правилу репо.

---

### Memory Hub / API памяти

- Единый фасад `MemoryHub` (`core/memory/`): `append_chat`, `list_chat`, `search_semantic`, `get_person` / `update_person_fact`, diary/journal/WM CRUD, prune/summarize hooks, stats.
- **Concurrency:** один writer-контур на процесс (sync `sqlite3` + lock **или** `aiosqlite`); запрет гонок chat_log / facts. Решение зафиксировать в ADR.
- Internal API `/v1/memory/*`: search (semantic), chat recall, write/add через Hub, people, stats, policies, prune/summarize — **без** обхода Hub.
- Агент, reflection, emotional layer, working memory, ltm_maintenance — только Hub.
- Миграции: таблица `schema_migrations` / версия схемы; init при старте ядра.

### Tools

- Сохранить/адаптировать: `search_memory` → semantic через Hub; `remember_knowledge`; `update_person_fact`; `get_person_info`.
- **Обязательно:** tool хронологического recall — `recall_chat` (или `search_memory(mode=chronological)`): канал/user, limit/offset или «N сообщений назад». Brain должен уметь вызывать это без RAG.
- Эвристики агента («вспомни…») сначала бьют в `list_chat` / `recall_chat`, при «про что мы говорили про X» — в semantic.

### Fast-Path (умный дом / короткие команды)

Не блокировать свет/замок полным brain+RAG, если команда однозначна:

- До или параллельно с brain: лёгкий классификатор / regex+intent (или tiny local model) → `home.*` / tool напрямую.
- Hub: STM / последние N из chat_log для «выключи то же» / «ещё раз»; semantic RAG для Fast-Path **не** обязателен.
- Полный brain — только если Fast-Path не уверен или нужен диалог.
- Конфиг-ориентир: `agent.fast_path_enabled`, `agent.fast_path_intents` (или секция `fast_path.*`); детали в ADR.
- Критерий: типовая команда умного дома без лишнего round-trip в deep/RAG при высокой уверенности.

---

### SQLite

- Один файл: `memory/neyra_memory.db` (+ возможные `-wal` / `-shm` при WAL mode).
- Таблицы минимум: `chat_log`, `people`, `person_facts`, `diary_notes`, `journal_entries`, working-memory rows/snapshots, `schema_migrations`, опц. `semantic_outbox` (что ещё не ушло в Chroma).
- **Chat log:** `ts`, `role`, `user_id`, `display_name`, `channel_id`, `source`, `text`, `turn_id`, `latency_ms`, emotions/mood, `meta` JSON (model lanes, tools, sounds).
- STM = короткое окно; «10 сообщений назад» → SQL `list_chat`, не cosine.

### Backup и git

- `neyra_memory.db`, `*-wal`, `*-shm`, `chroma_db/` — в `.gitignore` (секреты/PII), не в git.
- `backup_manager` / ручной бэкап: архивировать **SQLite + Chroma** (+ опц. export), не только «папку json».
- В репо допустимы пустые placeholder’ы каталогов (`memory/` keep), не сама БД.

---

### Chroma (перепрофилирование)

- Только семантический индекс; `metadata.type` ∈ {`knowledge`, `dialog_digest`, `person_fact`, `diary_note`, `journal_summary`, `working_memory`, `emotion_note`, …} + `person_id` / `channel_id` / `ts` / `pinned` / `source_row_id`.
- Письмо в индекс строго по `rag_write_mode`; raw full-chat dialog embed — **запрещён** после cutover.
- Prune / cluster merge / summarize — поверх Hub (истина в SQLite, индекс синхронизировать/чистить согласованно).
- **Векторный бэкенд:** на этапе 1A — Chroma. Интерфейс Hub (`search_semantic`) не должен жёстко зависеть от Chroma API снаружи адаптера — чтобы на этапе 4 можно было опционально заменить/дополнить (**sqlite-vss** / другой local ANN) без переписывания агента. На 1A **не** внедрять sqlite-vss — только шов адаптера.

---

### Event Bus (после Hub)

Не потерять контракты плагинов/webhooks:

| Событие | Политика |
|---------|----------|
| `memory.short_term_update` | оставить или alias; payload стабильный |
| `memory.long_term_write` | = semantic index write / digest; не путать с chat_log |
| `memory.journal_updated` | после journal в SQLite |
| `memory.working_memory_updated` | после WM в SQLite |
| **`memory.chat_log_append`** (новое) | после записи хода в chat_log |

Документировать в ADR; подписчики Discord/notify обновить при смене имён (aliases на переходный релиз допустимы).

---

### Debug / MCP / Dashboard

После Hub обязаны отражать правду:

- `GET /v1/debug/memory` и `/v1/memory/stats` — counts SQLite (chat_log, people, diary, …) + Chroma collection stats + `rag_write_mode`.
- MCP debug (`inspect_memory` и аналоги) — тот же контракт, не старые json paths.
- Dashboard memory widgets — не показывать «файловая PeopleDB», если primary уже SQLite.

---

### Cutover: legacy-импорт полностью упразднён (done)

**Политика legacy:** поддержка json/jsonl/md как *primary*-стора и dual-write были **временными** (миграция / тестовый контур на ветке 1A). Пользователь подтвердил, что переносить по факту нечего — поэтому вместо «оставить импорт как safety-net» legacy-файловая память **упразднена полностью**: ни ручного, ни автоматического импорта не осталось.

Итоговое состояние:

1. Cutover-флаги `hub_legacy_import` / `hub_legacy_fallback` / `hub_dual_write_legacy` **удалены** из кода (`core/memory/hub.py`, `core/memory/legacy.py`, `core/reflection.py`, `core/agent.py`) и из конфигов (`config.example.yaml`, `config.yaml`, `/v1/memory/policies`, `MemoryHub.stats()`, frontend types).
2. При подключённом `MemoryHub` people/diary/journal/WM пишутся и читаются **только через SQLite** — никакого fallback на json/jsonl/md чтения и никакого dual-write.
3. **Удалено, а не оставлено как safety-net:** `core/memory/legacy_import.py` (весь модуль), `run_hub_legacy_import()`, `POST /v1/memory/import-legacy`, marker-gated авто-импорт на старте. `_init_people_db` теперь смотрит только на `hub.stats()["people"]` / `people_db._cache` — никакого `people_db/*.json` glob.
4. Тонкие read/write-обёртки (`PeopleDB`, `NeyraDiary`, `ReflectionEngine`, WM helpers) сохранены, но `PeopleDB`/`NeyraDiary` больше вообще не делают файловый I/O (ни чтение, ни запись) — только in-memory `_cache`/список без Hub (консольный/аварийный сценарий, без персистентности). `ReflectionEngine._journal` стартует пустым и гидрируется только из Hub (`newest_first=True` + reverse в RAM); без Hub journal/diary остаются только в RAM процесса (ни `journal.json`, ни JSONL не пишутся и не читаются). `reflection_last.json` — по-прежнему debug-артефакт последнего reflect.

После cutover **не существует** как источник данных (файлы никогда не читаются; без Hub — только RAM):

| Было | Статус после cutover |
|------|----------------------|
| `memory/people_db/*.json` | не существует как источник; PeopleDB не читает и не пишет JSON |
| `memory/neyra_diary.jsonl` | не существует как источник; NeyraDiary не читает и не пишет JSONL; reflect без Hub → `agent.diary` RAM |
| `memory/journal.json`, `reflection_last.json` как истина | не primary; `journal.json` не пишется; `reflection_last.json` — debug dump последнего reflect |
| `memory/working_memory*.md` | не primary (без Hub — опц. `.md` для консоли) |
| Raw dialog rows в Chroma «на каждый ход» | запрещены |
| Cutover-флаги `hub_legacy_import/fallback/dual_write` | **удалены** из кода и конфига |
| `run_hub_legacy_import()` / `POST /v1/memory/import-legacy` / auto-import | **удалены полностью** (не safety-net, а упразднены) |

---

### Рефакторинг и чистка `core/` (фаза 1B)

**Трек:** ветка `feat/core-layout-1b` / [PR #6](https://github.com/KORESHon/Neyra-AIAssist/pull/6). **Не трогать контракты Memory Hub** без нужды — 1A уже в `main`. Цель 1B: читаемая раскладка пакетов + единый plugin surface, без поведенческих регрессий.

**Правила фазы:**
- Совместимость импортов: старые пути (`core.plugin_loader`, `core.llm_profile`, …) остаются как **тонкие re-export shim** минимум на один релиз после раскладки; канон — новые пакеты.
- Не менять External API / Event Bus имена событий.
- Не раздувать scope: Fast-Path / этап 2 / sqlite-vss — **вне** 1B.
- После каждого логического шага: `python -m compileall -q core interfaces scripts main.py` + memory smokes + `scripts/healthcheck.py`.
- Split / глубокий рефакторинг — **фаза 1R**, не 1B.

#### Целевая раскладка

| Пакет | Что переезжает | Статус |
|-------|----------------|--------|
| `core/memory/` | Hub/SQLite/Chroma + helpers | ✅ `stores.py` (+ shim `legacy.py`) |
| `core/plugins/` | loader / config / sdk / builder | ✅ + flat shims `core.plugin_*` |
| `core/llm/` | profile / retry / openrouter_balance | ✅ + flat shims; lazy `__init__` |
| `core/runtime/` | server / health / win_runtime / secrets | ✅ + flat shims; lazy heavy exports |
| `core/voice/` | STT + Yandex TTS | ✅ канон; root `stt`/`yandex_tts` — shims |
| `core/agent/` | оркестрация из монолита `agent.py` | → **фаза 1R** |
| `core/` root leftovers | `tools`, `reflection`, `working_memory`, … | пакеты/переименования → **фаза 1R** |

Оставить на корне после 1B (до 1R): `event_bus.py`, `tools.py`, `reflection.py`, `working_memory.py`, `emotional_layer.py`, `backup_manager.py`, `identity.py`, `mcp_client.py`, `external_storage.py`, `timeutil.py`, `vision_util.py`, `ltm_maintenance.py`, `agent.py` (+ flat shims пакетов).

#### Чеклист задач 1B (порядок выполнения)

| # | Задача | Done when | Статус |
|---|--------|-----------|--------|
| 1 | **`core/plugins/` (plugin_manager)** | path jail / `rollback_plugin` / reload живы; API через пакет | `[x]` |
| 2 | **Shim-слой плагинов** `core/plugin_*.py` | старые импорты не ломаются | `[x]` |
| 3 | **`core/llm/`** + shims + lazy `__init__` | resolve_*/backoff без регрессии; shim не тянет httpx | `[x]` |
| 4 | **`core/runtime/`** + shims + lazy server/health | `main` / healthcheck зелёные; secrets лёгкий | `[x]` |
| 5 | **`core/voice/` унификация** | канон `core.voice.*`; root shims | `[x]` |
| 6 | **Memory naming:** `legacy.py` → `stores.py` | smokes зелёные; alias `legacy` на один релиз | `[x]` |
| 7 | **Чистка dual-write / hub_legacy в коде** | в `.py` нет флагов/import-legacy (кроме assert/docs в smokes) | `[x]` |
| 8 | **Импорты потребителей** | канон или shim; `main` + Internal API на каноне | `[x]` |
| 9 | **Доки** ADR-0002 + PLAN | канон vs shim понятен | `[x]` |
| 10 | **Приёмка offline** | compileall + memory smokes + healthcheck + Auto Review | `[x]` 2026-07-25 |

Split `agent.py` / глубокий рефакторинг / «расфасовка по полкам» — **не в 1B**, см. **фазу 1R**.

#### Вне scope 1B

- Фаза **1R** (split монолитов, переименования, аудит костылей, раскладка остатков)
- Fast-Path / этап 2 / sqlite-vss / frontend redesign

---

### Фаза 1R — глубокий рефакторинг `core/` (после merge 1B)

**Трек:** ветка `feat/core-refactor-1r` / [PR #7](https://github.com/KORESHon/Neyra-AIAssist/pull/7).

**Суть (простыми словами):** да, «расфасовать по полкам» — большие файлы режем на логические модули, даём файлам понятные имена, раскладываем по подпапкам `core/`, попутно вычищаем костыли и баги. Это уже не package-move 1B, а полный рефакторинг кода.

**Правила 1R:**
- Поведение снаружи (API, Event Bus, Discord UX) не менять без явной причины в PR.
- После каждого крупного split: `compileall` + memory smokes + healthcheck; Auto Review.
- Compat shims 1B снимать только когда все callers переведены на канон.
- Не трогать контракты Memory Hub без ADR.

#### Чеклист 1R (стартовый)

| # | Задача | Done when | Статус |
|---|--------|-----------|--------|
| 1 | Inventory: монолиты и «корень `core/`» (`agent.py`, `tools.py`, `reflection.py`, …) | список файлов + целевые пакеты/имена в PLAN/PR | `[x]` см. карту ниже |
| 2 | Split `agent.py` → `core/agent/` (prompt / turn / tools wiring / …) | `NeyraAgent` API стабилен; smokes зелёные | `[~]` пакет + полки (`prompts`, people/speakers/events/chat_log, `tool_heuristics`); оркестрация ещё в `neyra.py` (~2k) |
| 3 | Рефакторинг/переименование остальных крупных модулей по назначению | имена = роль; мёртвый код убран | `[~]` `reflection/`, `tools/`, memory WM/emotion/ltm, `runtime` mcp/backup; дальше — дорезка / аудит |
| 4 | Аудит костылей/багов (костыли после 1A/1B, дубли, опасные пути) | findings закрыты или задокументированы | `[ ]` |
| 5 | Финальная раскладка по подпапкам `core/` + сужение/снятие shims 1B/1R | канонические импорты везде критичных callers | `[ ]` |
| 6 | Доки (ADR-0003 или раздел PLAN) + приёмка | compileall + smokes + healthcheck + Auto Review; Discord на стенде | `[ ]` |
| 7 | Удалить дубли файлов в корне `core/` (flat shims 1B/1R после перевода callers) | в корне `core/` нет «теневых» копий/`*.py`-shim'ов для уже перенесённых модулей; импорты только канонические | `[ ]` |

#### Inventory / целевая карта (1R)

| Сейчас (корень `core/`) | ~строк | Цель |
|-------------------------|--------|------|
| `agent.py` → **`core/agent/`** | ~2k в `neyra.py` | ✅ пакет + полки incl. `tool_heuristics`; дальше — vision/LLM setup / chat turn |
| `reflection.py` → **`core/reflection/`** | ~720 | ✅ пакет: `engine.py` (+ `__init__` → `ReflectionEngine`) |
| `ltm_maintenance.py` | ~450 | ✅ `core/memory/ltm_maintenance.py` (+ flat shim → задача 7) |
| `tools.py` → **`core/tools/`** | ~420 | ✅ пакет: `builtins.py` (+ `__init__` → `ALL_TOOLS` / `init_tools`) |
| `mcp_client.py` | ~340 | ✅ `core/runtime/mcp_client.py` (+ flat shim → задача 7) |
| `working_memory.py` | ~210 | ✅ `core/memory/working_memory.py` (+ flat shim → задача 7) |
| `emotional_layer.py` | ~115 | ✅ `core/memory/emotional_layer.py` (+ flat shim → задача 7) |
| `backup_manager.py` | ~95 | ✅ `core/runtime/backup.py` (+ flat shim → задача 7) |
| `timeutil.py` / `event_bus.py` / `identity.py` / … | <100 | оставить или тонкий `core/runtime` / `core/common` по мере нужды |
| flat shims 1B/1R (`plugin_*`, `llm_*`, `server`, WM, …) | — | **задача 7:** удалить дубли после перевода callers |

---

### Критерии приёмки

**Фаза 1A** *(принято в `main` через [PR #1](https://github.com/KORESHon/Neyra-AIAssist/pull/1))*

- [x] SQLite init/migrate; chat_log на каждый ход параллельно STM. *(пакет `core/memory/`, dual-write из agent)*
- [x] Tool/API `recall_chat` / chronological list — «N сообщений назад» без RAG. *(фильтр `user_id` и/или `channel_id` обязателен)*
- [x] People / diary / journal / WM через Hub → SQLite. *(Hub write/read: people, diary+reflect input, journal, WM, chat_log для small/hourly reflection; при подключённом Hub — только SQLite, файловый dual-write отключён независимо от флага)*
- [x] Chroma: raw full-chat embed выключен по умолчанию (`rag_write_mode` ≠ `legacy_dialog`); knowledge через Hub.
- [x] `rag_write_mode` и пути из конфига (`sqlite_path`, `stm_max_messages`, …); example + local синхронизированы.
- [x] Event Bus: `memory.chat_log_append`; прежние `memory.*` сохранены (journal/WM/STM/LTM).
- [x] `/v1/memory/*`, `/v1/debug/memory` — Hub stats / recall / search / people / diary / journal; MCP + dashboard Hub counts. `POST /v1/memory/import-legacy` **удалён** (не заменён на 410 — endpoint не существует).
- [x] Cutover: флаги удалены, legacy-импорт (ручной и авто) удалён как класс — Hub json/jsonl/md никогда не пишет и не читает, даже без Hub (только in-memory cache), см. таблицу «Что осталось» в разделе Cutover.
- [x] Backup учитывает `.db` (+ wal/shm) и Chroma (`backup_manifest.json`).
- [x] Промпт talk/brain читает people / diary / WM через Hub (без legacy-fallback — cutover завершён).
- [x] Smoke: `test_memory_hub_smoke.py` + `test_memory_cutover_offline.py` переписаны под Hub-only (без `run_hub_legacy_import`/marker/gap-import тестов, добавлен smoke гидрации журнала >500 строк); live e2e chat→healthcheck на стенде — ещё нет.
- [x] Fast-Path умного дома — **отложено в этап 2** (решение зафиксировано: не блокирует cutover 1A; edge — с колонкой на этапе 4).
- [x] Финал 1A: legacy-импорт полностью абандонен (`core/memory/legacy_import.py` удалён, `run_hub_legacy_import`/`POST /v1/memory/import-legacy`/marker-gated авто-импорт убраны); при подключённом Hub file PeopleDB/Diary/journal/WM больше не пишутся (SQLite only); без Hub `PeopleDB`/`NeyraDiary` — чисто in-memory (без файлового I/O вообще); `ReflectionEngine` без Hub читает diary из `agent.diary` (RAM), а не JSONL, и не пишет `journal.json`. **Merged в main 2026-07-24.**

**Фаза 1B** *(принято в `main` через [PR #6](https://github.com/KORESHon/Neyra-AIAssist/pull/6), `1d61ed5`)*

- [x] `core/plugins/` (plugin_manager): loader/config/sdk/builder + path jail / reload / rollback; shims; lazy builder.
- [x] `core/llm/` + `core/runtime/` + унификация `core/voice/`; lazy heavy exports; импорты зелёные (канон или shim).
- [x] Memory naming (`stores.py` + alias) + нет `hub_legacy_*` / import-legacy в runtime-коде.
- [x] Offline приёмка: `compileall` + memory smokes + `healthcheck` + Auto Review SUCCESS.
- [x] Split `agent.py` / глубокий рефакторинг — **вынесены в фазу 1R** (не блокер 1B).

**Фаза 1R** *(трек: [PR #7](https://github.com/KORESHon/Neyra-AIAssist/pull/7))*

- [x] Inventory монолитов + целевая карта пакетов/имён.
- [~] Split `agent.py` и других крупных модулей «по полкам» *(agent shelves + `reflection/` + `tools/` + memory WM/emotion/ltm + runtime mcp/backup; дальше — дорезка `neyra.py`)*.
- [ ] Переименования по логическому назначению; аудит костылей/багов.
- [ ] Финальная раскладка в подпапки `core/`; сужение shims 1B/1R.
- [ ] Удалить дубли файлов в корне `core/` (flat shims после перевода callers на канон).
- [ ] `compileall` + memory smokes + healthcheck + Auto Review; Discord на стенде.
## Этап 2 — Дополнительные улучшения (пакет мелких задач)

*Бывший этап 1 — сдвинут после Memory Hub.*

Сделать по мере необходимости; можно распараллелить:

- **Pre-context «мысли»:** короткий релевантный блок из дневника/Hub перед основным ответом (поверх semantic RAG + people).
- **Персона в двух артефактах:** разделить «базу личности» и «внешность / визуал»; редактируемые файлы рядом с `assistant.system_prompt`.
- **Контролируемое архивирование сессии:** при переполнении контекста — явная политика дампа в Hub (diary/LTM digest) и «чистый» старт диалога.
- **Сверка практик безопасности:** не светить секреты, риски смешения данных между людьми — перекрёстно с `security-model.md` и документацией деплоя.

**Чек-лист (двухполушарный режим — регрессия после этапа 1):**

- [ ] `use_brain_model_for_vision: true` — вложение уходит в Nemotron (brain), talk опирается на сводку brain без отдельного VL-caption.
- [ ] `use_brain_model_for_vision: false` — caption через `vision_model`, затем brain/talk как раньше.
- [ ] Запрос на тестовый код / плагин — brain вызывает `delegate_to_deep_logic`.
- [ ] 429 на `memory_model` — backoff в логе, ядро не падает на одном вызове.

---

## Этап 3 — Web UI как WebSocket-мост к Event Bus

*Раньше шёл после автономии; поднят выше по очереди.*

**Зачем раньше автономии:** Web UI можно тестировать сразу на текущем сервере (Discord/API уже есть). Колонки как железа пока нет; полный self-host voice+LLM — тяжёлый и поздний контур с большим числом интеграционных ошибок.

**Цель:** браузер как полноценный real-time клиент шины событий — тот же класс **тонких клиентов**, что позже будет у колонки (этап 4). Transport заложить сейчас, чтобы колонка потом подключилась к готовому мосту.

- Двусторонний WS-мост `Web UI <-> Event Bus`.
- Браузер публикует события (чат, музыка, плагины) и подписывается на stream-ответы и статусы.
- Управление плагинами и чатом в одном transport-контуре.
- Задел под колонка/edge/desktop-приложение/android-приложение/ios-приложение: тот же WSS-контракт (аудио-чанки / текст / события) — без обязательной реализации edge в этом этапе.

**Критерии приёмки:**

- [ ] CLI не обязателен для повседневной эксплуатации.
- [ ] Реакция UI на операции и события в real-time.
- [ ] Контракт WS задокументирован так, что этап 4 может переиспользовать его для micro-client колонки.

---

## Этап 4 — Автономный сервер + тонкие клиенты (Voice / Runtime / колонка)

*Дальнее будущее; бывший «этап 3 автономии». Сдвинут после Web UI.*

**Статус ориентира:** нескорое будущее. Нет стабильного железа колонки для приёмки; много путей (local vs cloud STT/TTS/LLM) → много ошибок без стенда. Делать после зелёного WS-моста (этап 3) и Hub/ядра.

**Цель автономии (два равноправных режима):**

1. **Self-host:** всё нужное (LLM, STT, TTS, память, tools) крутится на **той же машине / своём сервере** — без обязательных внешних API.
2. **Фундамент Neyra:** если сервер слабый или так удобнее — подключить уже заложенные / популярные сервисы (OpenRouter и др. LLM, Deepgram/Yandex/… для voice, OpenRouter audio/STT-модели вроде **NVIDIA Nemotron** и аналоги).

Автономность ≠ «весь проект внутри колонки». Neyra = **один сервер** (дом / VPS); колонка / телефон / Web UI = micro-client с связью к серверу.

### Модель развёртывания

| Узел | Роль | Вычисления |
|------|------|------------|
| **Neyra Server** | ядро, Hub/память, LLM, STT/TTS (local **или** cloud), tools, Event Bus | тяжёлые |
| **Умная колонка / edge-клиент** | mic/speaker, wake-word; **Fast-Path** света/сцен локально | лёгкие |
| **Телефон / Web UI** | тонкий клиент по WSS (контракт этапа 3) | лёгкие |

**На колонке (edge):** свет/сцены локально; сложный диалог → WSS на сервер. Полный `core/` / Chroma / local LLM в колонку **не** ставятся.

**На сервере:** агент, Hub, профили моделей, voice backend по конфигу.

Связь с этапом 3: колонка — ещё один клиент того же WSS/Event Bus, не отдельный протокол.

---

### LLM: self-host или фундамент (не выполнено)

- Свои OpenAI-compatible эндпоинты (LM Studio, Ollama, vLLM, llama.cpp, GPU-бокс) через профили `base_url` + model id.
- Brain / talk / deep / memory / vision — независимо: cloud (OpenRouter и т.п.) **или** local/custom.
- Режим «только свой сервер моделей» без обязательного OpenRouter.
- Либо наоборот: слабый сервер → всё через фундамент Neyra (уже заложенные провайдеры).

### Voice: переключаемые STT / TTS (обязательно)

Один конфиг-переключатель провайдера на роль (`stt.provider` / `tts.provider` или секция `voice.*`) — **не** «только local» и не «только Deepgram».

| Режим | STT (распознавание) | TTS (озвучка) |
|-------|---------------------|---------------|
| **Local** | Whisper / faster-whisper (`local_voice`) на сервере | CosyVoice (GPU) / Silero / Piper (CPU) |
| **Cloud / сервис** | Deepgram, Yandex SpeechKit и др. популярные API | те же экосистемы / аналоги TTS API |
| **Фундамент LLM/audio** | модели через OpenRouter (напр. **NVIDIA Nemotron** и др. audio/ASR-capable), если подходит пайплайн | по мере появления в фундаменте — заложить слот провайдера |

Принципы:

- Слабый сервер → cloud STT/TTS или OpenRouter-ASR; мощный → local на той же машине.
- Фундамент: адаптеры под **популярные** сервисы озвучки и приёма звука + единый интерфейс `transcribe()` / `synthesize()`; конкретный список провайдеров расширяется без ломки агента.
- Колонка шлёт аудио на сервер; сервер выбирает backend по конфигу. Опц. крошечный edge-TTS только для Fast-Path «ок / включаю».
- Cloud и local — **равноправные** режимы, не «local основной + cloud костыль».

### Память и vision на сервере

- Hub / SQLite + Chroma — только на сервере.
- Vision — `vision_model` / плагин на сервере (local или cloud).
- **Опционально:** sqlite-vss через адаптер `search_semantic` (оценка wheels/миграции).

### Edge Fast-Path ↔ серверный Fast-Path

- Edge: свет/сцены без WSS при уверенности.
- Иначе → WSS → сервер (brain или серверный Fast-Path из этапа 1).
- Логировать bypass.

**Критерии приёмки:**

- [ ] Переключение STT: local ↔ cloud-сервис (хотя бы один, напр. Deepgram) без правки кода агента — только конфиг.
- [ ] Переключение TTS: local ↔ cloud-сервис — только конфиг.
- [ ] Слот/путь STT через OpenRouter (Nemotron или актуальный audio/ASR id) задокументирован или работает как один из providers.
- [ ] Хотя бы один профиль LLM на local/custom endpoint **или** полный прогон на фундаменте OpenRouter — оба режима описаны в example config.
- [ ] Self-host сценарий: ключевые роли (LLM + STT + TTS) могут работать без внешних API на одной машине (при наличии железа).
- [ ] Слабый сервер: те же роли через cloud/фундамент.
- [ ] Типовая «включи свет» на edge без LLM; сложный запрос — WSS → ответ (когда появится клиент/колонка).
- [ ] В колонку не требуется полный репозиторий Neyra.
- [ ] Приёмка колонки — когда есть устройство/стенд; до этого — контракт + серверные voice/LLM переключатели.

### Docker / one-click сервер (базовый контур выполнен частично)

- docker-compose / `run_neyra.bat` — подъём **сервера**.
- Документировать: дом vs облако + URL для thin-client; какие `voice.*` / `llm.*` ключи для local vs cloud.

---

## 5) Архитектурные артефакты (не выполнено)

- **ADR-документы:**
  - Единый `discord` плагин.
  - **Memory Hub v2** (SQLite truth + Chroma semantic index + chat log) — приоритет этапа 1.
  - Memory lifecycle policy (поверх Hub).
  - MCP integration model.
  - Sandbox/hot-reload/rollback policy.
- **Тестовые сценарии:**
  - e2e Discord text+music.
  - Memory Hub: chat_log write → list_chat; semantic search по `type`; people/diary/journal в SQLite; prune/summarize без сырого full-chat в Chroma.
  - WS bridge pub/sub.
  - MCP debug and client connectivity.

---

## 6) Чек-лист валидации после существенных изменений

- Backend compile: `python -m compileall -q core interfaces scripts main.py`
- Frontend build: `cd frontend && npm run build`
- Core healthcheck: `python scripts/healthcheck.py --mode core --skip-http`
- Lavalink JAR: `python scripts/fetch_lavalink.py`
- Event-driven smoke: chat → MUSIC_PLAY → queue → skip/pause/resume → stop/clear
- Memory Hub smoke (1A): SQLite migrate → chat_log → recall_chat/list_chat → semantic by `type` → `/v1/memory/*` + `/v1/debug/memory` + MCP inspect
- Event Bus smoke: chat_log_append + journal/WM events after Hub writes
- Memory lifecycle smoke: prune/summarize поверх Hub; no raw full-chat Chroma embeds; memory_model backoff
- Cutover check: json/jsonl/md не primary; backup включает `.db` (+ wal) и Chroma
- Two-hemisphere smoke: brain native vision / VL fallback; `delegate_to_deep_logic`
- Core layout smoke (1B): импорты после раскладки `core/` + `plugin_manager`; Discord resident
- MCP smoke: debug-server tools + runtime MCP client calls

---

## 7) Риски и контроль

- Риск: деградация качества при автоматическом prune/summarize.
  - Контроль: quality gates и выборочные проверки retrieval.
- Риск: миграция Memory Hub ломает старые пути (jsonl / raw Chroma dialogs) или Event Bus подписки.
  - Контроль: фазы 1A→1B; aliases событий; cutover-чеклист; smoke list_chat + semantic + debug/MCP.
- Риск: Fast-Path ложно срабатывает на неоднозначной фразе (умный дом).
  - Контроль: порог уверенности + fallback в brain; логирование bypass; allowlist интентов.
- Риск: расширение атакующей поверхности через MCP.
  - Контроль: allowlist серверов, sandbox-права, аудит действий.
- Риск: hot-reload может оставлять «грязное» состояние подписок.
  - Контроль: lifecycle hooks + обязательная очистка/перерегистрация listeners.

---

## 7.5) Баг-трекер / известные дефекты

*Обновлено по анализу `logs/system.log` после ночного стресса (2026-05-02 … 2026-05-03).*

### BUG-001 — Discord lyrics mode (форматирование)

- **Зона:** `interfaces/discord/bot.py` (стрим, превью, чанки) + `core/agent.py` (постобработка после стрима).
- **Статус:** ❌ Открыт.
- **Направление:** исправить постобработку после стрима, сохранение `\n` в `_extract_sound_tags`.

### BUG-002 — VL (vision): Alibaba `DataInspectionFailed`

- **Лог:** `Upstream error from Alibaba: InternalError.Algo.DataInspectionFailed: Input text data may contain inappropriate content`.
- **Статус:** ❌ Открыт.
- **Направление:** fallback VL-модель, смягчение промпта, другой vision-провайдер.

### BUG-003 — Vision (free): HTTP 429 и rate limit

- **Лог:** `google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream`.
- **Статус:** ❌ Открыт.
- **Направление:** платная/BYOK ключ, другая vision-модель, backoff.

### BUG-004 — LLM: first-token timeout (6s)

- **Лог:** `LLM first-token timeout | attempt=1/2 | timeout=6.0s`.
- **Статус:** ⚠️ Watch.
- **Направление:** поднять `primary_first_token_timeout_seconds` или оставить.

### BUG-005 — Discord Gateway: обрывы WebSocket

- **Лог:** `Attempting a reconnect`, `Cannot connect to host gateway-*.discord.gg:443`.
- **Статус:** ⚠️ Monitor.
- **Направление:** сеть, VPN, firewall.

### BUG-006 — Музыка: `music.play => failed`

- **Статус:** ❌ Открыт.
- **Направление:** санитизация query (убирать `<…>` эмодзи), Soundcloud источник.

### BUG-007 — Стабильность рантайма: частые перезапуски ядра

- **Лог:** несколько подряд полных стартов ядра за короткий интервал.
- **Статус:** ❌ Открыт.
- **Направление:** собрать exit-код, Windows Event, воспроизведение.

### Наблюдения (не регистрируем как баг)

- `davey is not installed, voice will NOT be supported` — ожидаемое предупреждение.
- **Health monitor OK** — периодические записи штатны.

---

## 7.6) Legacy и fallback (после полной миграции конфигов моделей)

Перед полным отказом от обратной совместимости удалить ветки после миграции всех деплоев:


| Механизм                                      | Назначение                                                   |
| --------------------------------------------- | ------------------------------------------------------------ |
| `openrouter.model` / `primary_model`          | Старый «главный» id → talk, с **warning**                    |
| `openrouter.reflection_model`                 | Fallback для memory, **warning**                             |
| `async_reflection.model` в YAML               | Игнорируется в пользу `memory_model`                         |
| Плоские ключи `openrouter.`* без вложенности  | Работают параллельно с вложенными блоками                    |
| `self.llm_primary` / `llm_primary_model`      | Совместимость со старым кодом; = talk                        |
| Корневой YAML-блок `vision:`                  | Ниже приоритета чем `openrouter.vision_model`, с **warning** |
| `DEPRECATED_MODEL_MAP`                        | Подмена устаревших id моделей OpenRouter                     |
| `SCREEN_PROXY_SECRET` → `screen_proxy_plugin` | Заглушка под будущий плагин                                  |


**Технический долг:**

- Упоминания «VL-ход» в логах — не влияют на конфиг.
- Локальный screen/vision — через `vision_model` и будущие плагины; отдельной заглушки в `interfaces/` нет.

---

## 8) Backlog (дальний горизонт)

- **Интеграция с Obsidian** — экспорт из Memory Hub (SQLite/Chroma digests) в vault как `.md` (через MCP или Python CLI).
- **Полировка и чистка мусора по всему проекту** — после этапа 1 (ядро/память): пройтись повторно по репо, докам, fallback и логам.
- **Клиенты (desktop / mobile-lite)** — полное ТЗ по созданию приложений и целевому виду в продакшене: [Google Docs](https://docs.google.com/document/d/10wjeJefCRuF1ujJ0bWCwKw2tB9BwjV2ejqqd1f-vMhg/edit?tab=t.0).
- Standalone `.exe` сборка / `server-core + lightweight clients`.
- **Настройка LLM из Web UI** (выбор модели, правка system prompt) — после hot-reload.
- Device-mode (AI station).
- Open-core модель расширений.
- Публичный demo/BYOK режим.