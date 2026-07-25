# PLAN.md — Глобальный архитектурный план Neyra-AIAssist

## 1) Стратегическая цель

Построить модульную, event-driven и локально-автономную AI-платформу, где:

- ядро (`core`) стабильно работает как оркестратор,
- интерфейсы реализованы как плагины,
- Web UI управляет системой в real-time через события,
- память управляется как полноценный lifecycle (а не просто накопление),
- интеграции масштабируются через MCP, без разрастания самописных адаптеров в ядре.

---

## 2) Базовые архитектурные принципы

- **Event-first:** межмодульное взаимодействие только через Event Bus контракты.
- **Plugin-first:** интерфейсная логика живёт в `interfaces/`, ядро остаётся универсальным.
- **Secure-by-boundary:** `core` защищён от прямой саморедактируемости; расширения — через sandbox в плагинной зоне.
- **Local-first runtime:** облачные API опциональны; целевой режим — свой сервер (дом / NAS / VPS). Устройства — тонкие клиенты.
- **MCP-native future:** внешние возможности подключаются стандартизированными MCP-серверами.

### Двухполушарная когнитивная схема (OpenRouter)

| Роль | Конфиг / факт на стенде | Назначение |
|------|-------------------------|------------|
| **Левое полушарие** | `brain_model.model` → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | Tool-loop, нативное зрение при `use_brain_model_for_vision: true` |
| **Правое полушарие** | `brain_model.model_deep` → `nvidia/nemotron-3-ultra-550b-a55b:free` | Глубокая логика / код через `delegate_to_deep_logic` |
| **Гиппокамп** | `memory_model` → `nvidia/nemotron-3-super-120b-a12b:free` | LTM / WM / рефлексия / emotional layer |
| **Talk** | `talk_model` → `qwen/qwen3-235b-a22b-2507` | Финальный ответ пользователю |

**Зрение:** `use_brain_model_for_vision: true` — картинки в brain (Nemotron); `false` — VL-caption через `vision_model`.  
**Rate limit:** `memory_model` — retry с backoff на 429/timeout.

---

## 3) Текущее состояние (сводно)

| Область | Состояние |
|---------|-----------|
| **Этап 1** (Memory Hub + layout + refactor) | ✅ в `main` — PR [#1](https://github.com/KORESHon/Neyra-AIAssist/pull/1), [#6](https://github.com/KORESHon/Neyra-AIAssist/pull/6), [#7](https://github.com/KORESHon/Neyra-AIAssist/pull/7) |
| **Память** | Hub SQLite = source of truth; Chroma = semantic index; `rag_write_mode=important_only`; STM=10 |
| **Ядро** | `core/neyra.py` (~700 строк) + пакеты `agent/` `memory/` `llm/` `plugins/` `reflection/` `runtime/` `tools/` `voice/`; flat shims сняты |
| **Канон импорта** | `from core.neyra import NeyraAgent` (lazy re-export: `from core.agent import NeyraAgent`) |
| **Интерфейсы** | Discord resident + Internal API (`:8787`) + dashboard; MCP debug-server |
| **ADR** | [0001](docs/adr/0001-memory-hub-v2.md) Hub · [0002](docs/adr/0002-core-layout-1b.md) layout · [0003](docs/adr/0003-core-refactor-1r.md) refactor |
| **Активный фокус** | **Этап 2** — точечные улучшения |

**Windows runtime:** `.venv_win` + `run_neyra.bat` → `scripts/neyra_win_launcher.ps1`.  
**Linux/WSL:** `run_neyra.sh` (`*.sh` → LF via `.gitattributes`); venv `.venv` или `~/neyra-venv` на `/mnt`.

---

## 4) Очередь этапов

| # | Этап | Статус |
|---|------|--------|
| **1** | Memory Hub v2 + реорганизация `core/` (фазы 1A → 1B → 1R) | ✅ done |
| **2** | Точечные улучшения (персона, pre-context, безопасность, Fast-Path, архив сессии) | ▶ **активный** |
| **3** | Web UI как WebSocket-мост к Event Bus | очередь |
| **4** | Автономный сервер + тонкие клиенты / колонка | дальнее будущее |

---

## Этап 1 — Memory Hub + реорганизация `core/` ✅

**Итог:** один Memory API (Hub), SQLite как истина, Chroma как индекс; `core/` читается по пакетам; оркестратор — `core/neyra.py`.

### Фазы (архив)

| Фаза | Фокус | Merge |
|------|--------|-------|
| **1A — Memory Hub** | SQLite Hub, chat_log, people/diary/journal/WM, cutover без legacy-импорта | [PR #1](https://github.com/KORESHon/Neyra-AIAssist/pull/1) · ADR-0001 |
| **1B — Core layout** | пакеты `plugins` / `llm` / `runtime` / `voice` / `memory.stores` | [PR #6](https://github.com/KORESHon/Neyra-AIAssist/pull/6) · ADR-0002 |
| **1R — Core refactor** | split монолитов, снятие shims, полки `core/agent/*` | [PR #7](https://github.com/KORESHon/Neyra-AIAssist/pull/7) · ADR-0003 · `1b873d0` |

### Модель памяти (действующая)

| Роль | Где |
|------|-----|
| Диалог (полный chat log) | SQLite |
| People / diary / journal / WM | SQLite |
| Semantic recall | Chroma (`metadata.type`, без raw full-chat embed) |
| STM | RAM / окно из chat_log (`stm_max_messages`) |
| Персона | `assistant.system_prompt` / файлы промпта — не в диалоговой памяти |

**Правило:** каждый ход → SQLite `chat_log`; в Chroma — только осмысленное по `rag_write_mode`. Промпт talk/brain читает people / diary / WM **только через Hub**.

### Раскладка `core/` (факт)

```
core/
  __init__.py
  neyra.py          # NeyraAgent
  agent/            # shelves: chat, chat_stream, turn_*, reply_*, bootstrap, …
  memory/ llm/ plugins/ reflection/ runtime/ tools/ voice/
```

### Конфиг памяти (ключи)

`memory.sqlite_path`, `chroma_db_path`, `rag_enabled`, `rag_top_k`, `rag_write_mode` (`off` \| `digest` \| `important_only`), `chat_log_retention_days`, `stm_max_messages`, `working_memory.*`, `emotional_layer.*`.

Cutover-флаги и legacy-импорт (`import-legacy`, json/jsonl primary) **удалены** — см. ADR-0001.

### Event Bus (память)

| Событие | Когда |
|---------|--------|
| `memory.chat_log_append` | запись хода в chat_log |
| `memory.short_term_update` | STM |
| `memory.long_term_write` | semantic / digest (не путать с chat_log) |
| `memory.journal_updated` / `memory.working_memory_updated` | после Hub write |

### Приёмка этапа 1 (закрыта)

- [x] Hub-only people/diary/journal/WM + chat_log; smoke + live MCP
- [x] `/v1/memory/*`, `/v1/debug/memory`, MCP inspect
- [x] Backup `.db` (+ wal/shm) + Chroma
- [x] Layout + refactor; Discord UX + WS `chat_stream` 2026-07-25
- [x] Fast-Path умного дома — **перенесён в этап 2** (не блокер 1)

---

## Этап 2 — Дополнительные улучшения ▶

Сделать по мере необходимости; можно распараллелить. После этапа 1 — следующий рабочий фокус.

### Задачи

- **Pre-context «мысли»:** короткий релевантный блок из дневника/Hub перед ответом (поверх semantic RAG + people).
- **Персона в двух артефактах:** «база личности» и «внешность / визуал»; редактируемые файлы рядом с `assistant.system_prompt`.
- **Контролируемое архивирование сессии:** при переполнении контекста — явная политика дампа в Hub (diary/LTM digest) и «чистый» старт.
- **Сверка практик безопасности:** секреты, смешение данных между людьми — с `security-model.md` и доками деплоя.
- **Fast-Path (умный дом):** лёгкий intent/regex до brain → `home.*` / tool; конфиг-ориентир `agent.fast_path_*` / `fast_path.*`; семантический RAG не обязателен. Edge-часть — с колонкой (этап 4).

### Чек-лист регрессии (двухполушарный режим)

- [ ] `use_brain_model_for_vision: true` — вложение в Nemotron (brain), talk на сводке.
- [ ] `use_brain_model_for_vision: false` — caption через `vision_model`, затем brain/talk.
- [ ] Запрос на код / плагин — brain вызывает `delegate_to_deep_logic`.
- [ ] 429 на `memory_model` — backoff в логе, ядро не падает.

---

## Этап 3 — Web UI как WebSocket-мост к Event Bus

**Зачем до автономии:** UI тестируется на текущем сервере (Discord/API уже есть); колонки как железа пока нет.

**Цель:** браузер = real-time клиент шины — тот же класс тонких клиентов, что позже у колонки (этап 4).

- Двусторонний WS-мост `Web UI ↔ Event Bus`.
- Публикация событий (чат, музыка, плагины) + подписка на stream/статусы.
- Задел под edge/desktop/mobile: тот же WSS-контракт (аудио / текст / события).

**Критерии приёмки:**

- [ ] CLI не обязателен для повседневной эксплуатации.
- [ ] UI реагирует на операции и события в real-time.
- [ ] Контракт WS задокументирован для переиспользования в этапе 4.

---

## Этап 4 — Автономный сервер + тонкие клиенты

**Ориентир:** после зелёного WS-моста (этап 3). Нет стабильного стенда колонки для приёмки.

Neyra = **один сервер**; колонка / телефон / Web UI = micro-client.

| Узел | Роль |
|------|------|
| **Neyra Server** | ядро, Hub, LLM, STT/TTS (local или cloud), tools, Event Bus |
| **Колонка / edge** | mic/speaker, wake-word; Fast-Path света/сцен локально |
| **Телефон / Web UI** | тонкий клиент по WSS (контракт этапа 3) |

### LLM

- OpenAI-compatible self-host (LM Studio / Ollama / vLLM / …) через профили `base_url` + model id.
- Роли brain / talk / deep / memory / vision — независимо cloud или local.
- Режим «только свой сервер» без обязательного OpenRouter — или слабый сервер → фундамент (OpenRouter и др.).

### Voice (переключаемые STT / TTS)

Один конфиг-переключатель на роль (`stt.provider` / `tts.provider` / `voice.*`):

| Режим | STT | TTS |
|-------|-----|-----|
| **Local** | Whisper / faster-whisper | CosyVoice / Silero / Piper |
| **Cloud** | Deepgram, Yandex SpeechKit, … | те же экосистемы |
| **Фундамент** | OpenRouter audio/ASR (напр. Nemotron) | по мере появления слота |

Cloud и local — равноправны. Колонка шлёт аудио на сервер; backend выбирается конфигом.

### Память / vision на сервере

- Hub + Chroma только на сервере.
- Опционально: sqlite-vss через адаптер `search_semantic` (без ломки агента).

### Критерии приёмки (черновик)

- [ ] STT/TTS: local ↔ cloud только конфигом.
- [ ] Слот STT через OpenRouter задокументирован или работает.
- [ ] Профиль LLM local/custom **или** полный прогон на OpenRouter — оба в example config.
- [ ] Self-host: LLM + STT + TTS без внешних API (при наличии железа); слабый сервер — через cloud.
- [ ] Edge «включи свет» без LLM; сложный запрос — WSS → сервер (когда появится клиент).
- [ ] В колонку не требуется полный репозиторий Neyra.

### Docker / launcher

- `docker-compose` / `run_neyra.bat` / `run_neyra.sh` — подъём сервера.
- Документировать: дом vs облако, URL thin-client, ключи `voice.*` / `llm.*` для local vs cloud.

---

## 5) Архитектурные артефакты

| Артефакт | Статус |
|----------|--------|
| ADR-0001 Memory Hub v2 | ✅ |
| ADR-0002 Core layout 1B | ✅ |
| ADR-0003 Core refactor 1R | ✅ |
| ADR: Memory lifecycle policy (поверх Hub) | [ ] |
| ADR: MCP integration model | [ ] |
| ADR: Sandbox / hot-reload / rollback | [ ] |
| ADR: единый discord-плагин (исторически) | частично (resident plugin уже есть) |

**Тестовые сценарии (поддерживать):**

- e2e Discord text (+ music при поднятом Lavalink)
- Memory Hub: chat_log → recall; semantic by `type`; people/diary/journal
- WS bridge pub/sub (этап 3)
- MCP debug + runtime MCP client

---

## 6) Чек-лист валидации после существенных изменений

- `python -m compileall -q core interfaces scripts main.py` (из `.venv_win` на Windows)
- `python scripts/test_memory_hub_smoke.py` + `test_memory_cutover_offline.py`
- `python scripts/healthcheck.py --mode core --skip-http`
- Frontend: `cd frontend && npm run build` (если трогали UI)
- Lavalink JAR: `python scripts/fetch_lavalink.py` (если музыка)
- Live (по возможности): MCP `/v1/chat` или Discord; `/v1/debug/memory`
- Auto Review на PR

---

## 7) Риски и контроль

- **Prune/summarize** портит retrieval → quality gates, выборочные проверки.
- **Fast-Path** ложно срабатывает → порог уверенности + fallback в brain; allowlist интентов.
- **MCP** расширяет атакующую поверхность → allowlist серверов, sandbox, аудит.
- **Hot-reload** оставляет грязные подписки → lifecycle hooks + очистка listeners.
- **Hub / Event Bus** — контракты не ломать без ADR (этап 1 закрыт; регрессии ловить smokes).

---

## 7.5) Баг-трекер / известные дефекты

*Исторический срез логов 2026-05; пути обновлены под раскладку 1R. Пересмотреть при следующем стресс-прогоне.*

| ID | Суть | Статус | Зона / направление |
|----|------|--------|---------------------|
| **BUG-001** | Discord lyrics: ломаются переносы строк | ❌ open | `interfaces/discord/bot.py` + постобработка стрима (`core/agent/reply_*`, `chat_stream`) |
| **BUG-002** | VL Alibaba `DataInspectionFailed` | ❌ open | fallback VL / другой провайдер / смягчение промпта |
| **BUG-003** | Vision free: HTTP 429 | ❌ open | BYOK / другая модель / backoff |
| **BUG-004** | LLM first-token timeout 6s | ⚠️ watch | `primary_first_token_timeout_seconds` |
| **BUG-005** | Discord Gateway reconnect | ⚠️ monitor | сеть / VPN / firewall |
| **BUG-006** | `music.play` failed | ❌ open | санитизация query, Soundcloud; нужен Lavalink |
| **BUG-007** | Частые перезапуски ядра | ❌ open | exit-код / Event Log / repro |

**Не баг:** `davey is not installed` (voice Discord); periodic Health monitor OK.

---

## 7.6) Legacy и fallback (модели / конфиг)

Перед полным отказом от обратной совместимости — вычистить после миграции всех деплоев:

| Механизм | Назначение |
|----------|------------|
| `openrouter.model` / `primary_model` | старый id → talk, warning |
| `openrouter.reflection_model` | fallback для memory, warning |
| `async_reflection.model` в YAML | игнорируется в пользу `memory_model` |
| Плоские ключи `openrouter.*` | параллельно с вложенными блоками |
| `self.llm_primary` / `llm_primary_model` | = talk |
| Корневой YAML `vision:` | ниже `openrouter.vision_model`, warning |
| `DEPRECATED_MODEL_MAP` | подмена устаревших id |
| `SCREEN_PROXY_SECRET` | заглушка под будущий плагин |

**Долг:** «VL-ход» в логах — косметика; screen/vision — через `vision_model` / плагины.

---

## 8) Backlog (дальний горизонт)

- Интеграция с Obsidian — экспорт из Hub в vault `.md` (MCP или CLI).
- Повторная полировка репо / доков / fallback / логов после этапа 2+.
- Клиенты desktop / mobile-lite — [Google Docs ТЗ](https://docs.google.com/document/d/10wjeJefCRuF1ujJ0bWCwKw2tB9BwjV2ejqqd1f-vMhg/edit?tab=t.0).
- Standalone `.exe` / server-core + lightweight clients.
- Настройка LLM из Web UI (модель, system prompt) — после hot-reload.
- Device-mode (AI station), open-core расширения, публичный demo/BYOK.
