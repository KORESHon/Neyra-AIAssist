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
| **Активный фокус** | **Этап 2** — 2A/2B + voice-конфиг готовы; дальше 2C→2D→2E→2F(код) · [PR #10](https://github.com/KORESHon/Neyra-AIAssist/pull/10) |

**Windows runtime:** `.venv_win` + `run_neyra.bat` → `scripts/neyra_win_launcher.ps1`.  
**Linux/WSL:** `run_neyra.sh` (`*.sh` → LF via `.gitattributes`); venv `.venv` или `~/neyra-venv` на `/mnt`.

---

## 4) Очередь этапов

| # | Этап | Статус |
|---|------|--------|
| **1** | Memory Hub v2 + реорганизация `core/` (фазы 1A → 1B → 1R) | ✅ done |
| **2** | Точечные улучшения (фазы 2A–2F; см. ниже) | ▶ **активный** · трек [PR #10](https://github.com/KORESHon/Neyra-AIAssist/pull/10) |
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

**Трек:** ветка `docs/stage-2-plan` / [PR #10](https://github.com/KORESHon/Neyra-AIAssist/pull/10) (план + реализация slice’ами в том же PR или follow-up).  
**Правила:** не ломать Hub / Event Bus без ADR; не раздувать scope до этапа 3 (полный WS UI) и этапа 4 (колонка / self-host voice stack). После каждого slice: `compileall` + memory smokes + healthcheck; при касании агента — Discord или MCP `/v1/chat`.

Фазы **можно распараллелить** (разные PR), кроме случаев явной зависимости (отмечено ниже).

### Статус задач (сводно)

| ID | Задача | Статус | Комментарий |
|----|--------|--------|-------------|
| **2A** | Persona pack (`persona.md` / `appearance.md`) | ✅ код | Осталось: smoke Discord/MCP на обычный чат |
| **2B** | Pre-context (diary + user-scoped WM) | ✅ код | `memory.pre_context.enabled` default **false**; semantic source — позже |
| **Voice cfg** | Канон `voice.stt`/`voice.tts` × prefer/enable + soft ERROR | ✅ | Фундамент для 2F; Auto Review majors закрыты |
| **2C** | Session archive (overflow / `/reset`) | ⬜ todo | Hub digest + STM policy + event bus |
| **2D** | Security pass | ⬜ todo | Секреты, user-scope recall, docs |
| **2E** | Fast-Path умного дома | ⬜ todo | Allowlist intents → `home.*`; user-scoped «ещё раз» |
| **2F** | OpenRouter Whisper STT (код провайдера) | 🟡 частич. | Конфиг/резолвер готовы; **нет** реального `STTEngine` OpenRouter + smoke |
| **Reg** | Регрессия этапа 2 (vision / Discord / MCP) | ⬜ todo | Прогон перед закрытием этапа |

**Осталось сделать (порядок рекомендуемый):**

1. **2C** — контролируемое архивирование сессии при overflow / `/reset`.
2. **2D** — security pass (чеклист + доки).
3. **2E** — Fast-Path home (серверный контур, не колонка).
4. **2F** — дописать провайдер OpenRouter в `STTEngine` + smoke на клипе.
5. **2A smoke** — Discord/MCP: обычный текст не деградирует.
6. **Регрессия этапа 2** — полный чеклист ниже перед merge/закрытием.

### Карта фаз

| Фаза | Фокус | Статус | Done when |
|------|--------|--------|-----------|
| **2A — Persona pack** | база личности + визуал как отдельные редактируемые артефакты | ✅ код / ⬜ smoke | два файла/ключа в промпт-пайплайне; example + local; smoke чат |
| **2B — Pre-context thoughts** | короткий «мысль/намёк» из Hub перед talk | ✅ | блок в system/context; выкл. флагом; WM только с `user_id` |
| **2C — Session archive** | политика при overflow STM/контекста | ⬜ | dump в Hub + trim/clean start; событие на шине |
| **2D — Security pass** | сверка секретов и границ людей | ⬜ | чеклист закрыт; нет утечек; доки |
| **2E — Fast-Path home** | короткие команды дома без полного brain+RAG | ⬜ | intent → `home.*`; fallback brain; smoke 2 users |
| **2F — Voice STT OpenRouter** | провайдер STT через OpenRouter Whisper | 🟡 cfg ✅ / код ⬜ | turbo clip smoke; soft ERROR; deepgram/groq/local OK |

**Отложено:** live mic-stream (realtime WebSocket ASR). Nemotron Omni на chat/completions — file/clip audio для «послушай и ответь», не выделенный STT endpoint; для транскрипта в этапе 2 берём **OpenRouter `/audio/transcriptions`** (фаза 2F). Live колонка / Deepgram live → этап 4.

---

### Фаза 2A — Persona pack (личность + визуал)

**Проблема сейчас:** характер и «как выглядеть / визуальный образ» свалены в один `assistant.system_prompt` — сложно править и опасно тащить визуал в каждый текстовый ход.

**Сделать:**

1. Разделить артефакты рядом с промптом (пути в конфиге, имена уточняемы):
   - `assistant.persona_path` / `persona.md` — характер, тон, границы, лексика.
   - `assistant.appearance_path` / `appearance.md` — внешность / визуальный канон (для vision/image-gen/описаний).
2. В talk/brain: persona всегда; appearance — только когда релевантно (vision, «как ты выглядишь», image tools) или короткий кап в промпт по флагу.
3. Сохранить обратную совместимость: если новых файлов нет — читать текущий `system_prompt` как сейчас.
4. Синхронизировать `config.example.yaml` ↔ `config.yaml`; кратко в HELP/ADR (можно короткий раздел в PLAN, отдельный ADR — по желанию).

**Не делать в 2A:** Web UI редактор персоны (этап 3); смена модели под визуал.

**Приёмка:**

- [x] Два артефакта на диске + ключи в example/local config (`prompts/*.example.md`, local `*.md` gitignored).
- [ ] Обычный текстовый чат не деградирует (smoke Discord/MCP).
- [x] Запрос про внешность / картинка — appearance подмешивается в talk (`include_appearance`).

---

### Фаза 2B — Pre-context «мысли»

**Проблема:** semantic RAG + people есть, но нет короткого «о чём я думаю / что сейчас важно» из дневника/Hub перед ответом — персона звучит менее цельно.

**Сделать:**

1. Перед talk (и опц. до brain): собрать **короткий** блок (лимит символов, напр. 400–800) из Hub:
   - diary (общий журнал ассистента) — global OK;
   - WM — **только** `working_memory_for_prompt(internal_user_id)` / эквивалент с обязательным `user_id` (не `latest_wm_snapshot(user_id=None)`);
   - semantic hits — с фильтром по `user_id` / person scope, где применимо; `type` diary/emotion/WM;
   - не полный dump journal.
2. Конфиг: `memory.pre_context.enabled`, `max_chars`, `sources` (diary/wm/semantic), `inject_lane` (talk | brain | both).
3. Пометить секцию в промпте явно (`PRE-CONTEXT` / «внутренний намёк»), чтобы модель не цитировала её как «из базы» дословно, если так зашито в persona.
4. Выключение одним флагом без поломки пайплайна.

**Зависимости:** опирается на Hub API этапа 1 (уже в main). Можно параллельно с 2A.

**Приёмка:**

- [x] Флаг off → поведение как сейчас.
- [x] Флаг on → блок `# PRE-CONTEXT` собирается (debug log); soft-fail при ошибках.
- [x] Нет раздувания промпта сверх `max_chars`.
- [x] WM только через `working_memory_for_prompt(internal_user_id)` — пустой uid → блок пропущен; semantic source пока skip (нет user metadata API).

---

### Фаза 2C — Контролируемое архивирование сессии

**Проблема:** при overflow контекста сейчас trim STM «вполсилы»; нет явной политики «запомнить важное → начать чище».

**Сделать:**

1. Политика при `context_length_exceeded` / ручном `/reset` / пороге STM:
   - опциональный digest хода/окна → Hub (diary note и/или LTM digest через существующий summarize-контур);
   - затем trim STM / «clean start» по флагу.
2. Конфиг: `memory.session_archive.on_overflow`, `on_manual_reset`, `write_diary`, `write_ltm_digest`, `clear_stm_after`.
3. Event Bus: например `memory.session_archived` (payload: reason, user_id, channel_id, chars) — для UI этапа 3.
4. Не дублировать raw full-chat в Chroma (только digest / important — как `rag_write_mode`).

**Зависимости:** желательно после или вместе с проверкой текущего overflow-retry в `chat_stream` (уже есть trim + shrink prompt).

**Приёмка:**

- [ ] Симулированный overflow или ручной reset пишет в Hub ожидаемый артефакт (при включённых флагах).
- [ ] STM после политики соответствует `clear_stm_after`.
- [ ] Событие на шине (если ввели) видно в debug/fire_event или подписчике.

---

### Фаза 2D — Security pass

**Проблема:** после cutover/refactor нужно явно сверить границы, а не полагаться на «вроде ок».

**Сделать (чеклист-проход + точечные фиксы):**

1. Секреты: `.env` / `apply_env_secrets`; Internal API anon vs token; не светить ключи в логах, dashboard, MCP `read_config` (уже маскирует — проверить регрессии).
2. Изоляция людей: prompt/tools не должны отдавать чужие facts по ошибке id; `recall_chat` всегда с `user_id` и/или `channel_id`.
3. Plugin sandbox / path jail — smoke на попытку выхода из `interfaces/`.
4. Документы: `security-model.md` + краткий ops-раздел «что не коммитить / что в backup».
5. Free Omni endpoint: не слать PII/голоса/лица на `:free` NVIDIA trial без согласия (предупреждение в доке voice/vision).

**Приёмка:**

- [ ] Чеклист выше пройден, findings закрыты или заведены в §7.5 как BUG.
- [ ] Нет секретов в свежем `logs/system.log` после тестового чата.
- [ ] Доки обновлены.

---

### Фаза 2E — Fast-Path (умный дом)

**Проблема:** однозначные команды («выключи свет») не должны ждать полный brain+RAG.

**Сделать:**

1. До или параллельно с brain: лёгкий классификатор (regex + allowlist intent **или** tiny heuristic) → прямой tool / событие `home.*`.
2. Конфиг: `agent.fast_path.enabled`, `intents` / `fast_path.*` (patterns → action).
3. При низкой уверенности — полный brain как сейчас.
4. Hub: для «ещё раз / то же» — STM и/или `list_chat` / `recall_chat` **всегда** с фильтром `user_id` и/или `channel_id` (тот же контракт, что в 2D); semantic RAG **не** обязателен.
5. Логировать bypass (`fast_path.hit` / reason) для отладки ложных срабатываний.
6. Edge Fast-Path на колонке — **не** в этапе 2 (этап 4); здесь только серверный контур.

**Приёмка:**

- [ ] 2–3 типовые фразы из allowlist срабатывают без deep/RAG (видно в логе).
- [ ] Неоднозначная фраза → brain, не ложный home-action.
- [ ] Smoke: два пользователя — Fast-Path «ещё раз» видит только свой хвост chat_log.
- [ ] example + local config sync; выкл. флагом = старое поведение.

---

### Фаза 2F — Voice STT: OpenRouter Whisper

**Проблема:** в `core/voice/stt.py` (`STTEngine`) уже есть local faster-whisper, Groq и Deepgram, но нет провайдера через тот же ключ OpenRouter, что и LLM. Нужен дешёвый облачный STT без отдельного Deepgram/Groq ключа.

**Целевая модель:** `openai/whisper-large-v3-turbo` (~$0.04 / час аудио; duration-based).  
**Дока:** [OpenRouter Speech-to-Text](https://openrouter.ai/docs/guides/overview/multimodal/stt) — `POST https://openrouter.ai/api/v1/audio/transcriptions`.

**Канон конфига (важно):** единый корень `voice`; STT и TTS **независимо** (без глобального `is_local`):

```yaml
voice:
  language: "ru"
  stt:
    prefer: cloud            # cloud | local — первый выбор, если оба enable
    local:  { enable: false, model: small, device: cpu }
    cloud:  { enable: true, provider: deepgram|groq|openrouter, ... }
  tts:
    prefer: cloud
    local:  { enable: false, provider: "" }
    cloud:  { enable: true, provider: yandex, ... }
```

Правила: один `enable` → его lane; оба → `prefer` затем fallback; оба выкл./не настроены → **soft ERROR** в логе (STT/TTS off), **ядро не падает**.  
`STTEngine` / TTS читают через `core/voice/config.py` (`resolve_stt_runtime` / `resolve_tts_runtime`).  
Legacy `voice.is_local` / flat `voice.stt` / `voice_cloud` ещё нормализуются в памяти, но в example/local больше не пишем.

**Контракт API (зафиксировать в коде):**

1. Auth: тот же Bearer, что LLM (`OPENROUTER_API_KEY` → `openrouter.api_key`).
2. Два пути входа (оба поддерживать или явно выбрать один + fallback):
   - **JSON:** `{ "model", "input_audio": { "data": "<raw base64>", "format": "wav|mp3|…" }, "language"? }` — base64 = сырые байты, не data-URI.
   - **multipart** (OpenAI-compatible): `file` + `model` (+ `language`), лимит 25 MB.
3. Ответ: `{ "text", "usage": { "seconds", "cost", … } }`; логировать `usage.seconds` / `usage.cost` на debug, не светить ключ.
4. Опции: `language` (default `ru`), `temperature` по желанию; `response_format=json` (default). Upstream timeout ~60s — резать/чанкить длинные клипы.
5. Форматы: как минимум `wav`, `mp3`, `webm`, `ogg` (Discord/браузер).

**Сделать в коде:**

1. Дописать провайдер OpenRouter в `STTEngine` (резолв уже через `voice.stt`):
   - `voice.stt.cloud.enable: true` + `voice.stt.cloud.provider: openrouter` (+ `prefer: cloud` или единственный enable).
   - `voice.stt.cloud.openrouter.model` default `openai/whisper-large-v3-turbo`.
   - `base_url` из `openrouter.base_url` или `https://openrouter.ai/api/v1`.
   - лог `STT(OpenRouter): model=… | key_source=…` (без ключа).
2. Переиспользовать `transcribe(path|bytes)` — плагины не должны знать про OpenRouter.
3. Ошибки: 401/429/timeout → soft ERROR + опц. fallback на `voice.stt.local` (если enable); ядро не крашить.
4. Короткий smoke на тестовом wav → непустой `text` + cost в логе.
5. Дока: ссылка на OpenRouter STT; цена ~4¢/час; это **file/clip**, не live mic.

**Не делать в 2F:**

- Live/streaming ASR (WebSocket mic) — этап 4.
- TTS через OpenRouter (отдельный трек / этап 4).
- Nemotron Omni chat+audio как замена Whisper.
- Обязательный default стенда на openrouter (достаточно поддержки в коде + example; стенд можно переключить осознанно).

**Конфиг + `.env` (структура, обязательно в том же slice):**

Синхронизировать и привести к одной понятной схеме:

| Файл | Что сделать | Статус |
|------|-------------|--------|
| `config.example.yaml` / `config.yaml` | **`voice.stt` / `voice.tts`**: `prefer` + `local/cloud.enable`; без `voice_cloud` / без `is_local`. | ✅ |
| `.env.example` / `.env` | Комментарии под modality + `stt.cloud.provider`; секреты сохранить. | ✅ |
| `core/runtime/secrets.py` | Deepgram/Groq → `voice.stt.cloud.*.api_key` (только если modality уже в YAML); Yandex → `voice.tts.cloud`; OpenRouter → `openrouter.api_key`. Не создавать пустой `voice.cloud`. | ✅ |
| `core/voice/config.py` | Резолвер + soft ERROR + legacy normalize. | ✅ |
| `STTEngine` OpenRouter provider | Реальный вызов `/audio/transcriptions` + fallback local | ⬜ |

**Приёмка:**

- [ ] `stt.cloud.enable` + `provider=openrouter` + turbo → короткий клип; лог `STT(OpenRouter): …`.
- [ ] Ключ только из `OPENROUTER_API_KEY` / `openrouter.api_key`.
- [ ] `provider=deepgram|groq` и `stt.local.enable` (faster-whisper) без регрессий.
- [x] Оба `enable=false` / нет ключей → soft ERROR, ядро стартует.
- [x] Нет отдельного `voice_cloud` в example/local; `STTEngine` читает через `resolve_stt_runtime`.
- [x] `.env*` структурированы; в логах нет API key.
- [ ] Дока: https://openrouter.ai/docs/guides/overview/multimodal/stt (+ краткая заметка в config-reference).

---

### Регрессия этапа 2 (прогон перед закрытием этапа)

- [ ] `use_brain_model_for_vision: true` — вложение в Nemotron (brain), talk на сводке.
- [ ] `use_brain_model_for_vision: false` — caption через `vision_model`, затем brain/talk.
- [ ] Запрос на код / плагин — brain вызывает `delegate_to_deep_logic`.
- [ ] 429 на `memory_model` — backoff в логе, ядро не падает.
- [ ] Discord text stream + MCP `/v1/chat` без регрессий после merge фаз.
- [ ] STT: openrouter turbo на тестовом клипе (если ключ есть); остальные engines не сломаны.

### Вне scope этапа 2

- Полный Web UI WS-мост (этап 3).
- Live mic ASR / колонка / полный self-host voice stack (этап 4) — **file/clip** OpenRouter STT как раз в 2F.
- sqlite-vss, Obsidian export, desktop/mobile клиенты.
- Nemotron Omni как live микрофонный STT.

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
| **Фундамент** | OpenRouter `/audio/transcriptions` (Whisper turbo — фаза **2F**); live mic — отдельные live-провайдеры | слот провайдера без ломки агента |
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
