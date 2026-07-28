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

**Зрение:** `use_brain_model_for_vision: true` — картинки в brain (Nemotron); `false` — VL-caption через `vision_model`. Live-проверка картинки — smoke при работе над UI/клиентами (не блокер закрытия прошлых этапов).  
**Rate limit:** `memory_model` — retry с backoff на 429/timeout.

---

## 3) Текущее состояние (сводно)

| Область | Состояние |
|---------|-----------|
| **Закрытые этапы (архив)** | **ex-1** Memory Hub + layout/refactor · **ex-2** persona/pre_context/archive/security/fast_path/OpenRouter STT — в `main` после merge [PR #10](https://github.com/KORESHon/Neyra-AIAssist/pull/10) (+ [#1](https://github.com/KORESHon/Neyra-AIAssist/pull/1), [#6](https://github.com/KORESHon/Neyra-AIAssist/pull/6), [#7](https://github.com/KORESHon/Neyra-AIAssist/pull/7)) |
| **Память** | Hub SQLite = source of truth; Chroma = semantic index; `rag_write_mode=important_only`; STM=10; scoped RAG; session_archive |
| **Ядро** | `core/neyra.py` + пакеты `agent/` `memory/` `llm/` `plugins/` `reflection/` `runtime/` `tools/` `voice/` |
| **Голос** | `voice.stt`/`voice.tts` modality + soft ERROR; STT: local / Deepgram / Groq / **OpenRouter Whisper** |
| **Агент** | persona/appearance packs; optional PRE-CONTEXT; Fast-Path `home.*` (сервер); security-model |
| **Интерфейсы** | Discord resident + Internal API (`:8787`) + dashboard; MCP debug-server |
| **ADR** | [0001](docs/adr/0001-memory-hub-v2.md) Hub · [0002](docs/adr/0002-core-layout-1b.md) layout · [0003](docs/adr/0003-core-refactor-1r.md) refactor |
| **Активный фокус** | **Foundation polish + soak** — Discord + music ~сутки на Windows, затем mini-PC. Этапы 1–2 (WS UI / автономия) — **позже** |

**Windows runtime:** `.venv_win` + `run_neyra.bat` → `scripts/neyra_win_launcher.ps1`.  
**Linux/WSL:** `run_neyra.sh` (`*.sh` → LF via `.gitattributes`); venv `.venv` или `~/neyra-venv` на `/mnt`.

### Архив: что уже сделано (кратко)

**ex-Этап 1 — Memory Hub + реорганизация `core/`** ✅  
Hub SQLite (chat_log / people / diary / journal / WM), Chroma как индекс, cutover без legacy-импорта; пакетная раскладка `core/`; оркестратор `core/neyra.py`. ADR-0001…0003. PR #1 / #6 / #7.

**ex-Этап 2 — Точечные улучшения** ✅ (merge PR #10)  
Persona/appearance; PRE-CONTEXT (user-scoped WM); session archive (scoped `chat_log`); security pass (scoped RAG, MCP redact, ContextVar turn-scope); voice modality + OpenRouter Whisper STT; Fast-Path allowlist → `home.*` (сервер; multi-client/колонка → этап 2, позже). Discord/MCP smokes закрыты. Vision live-картинка — optional smoke ниже.

---

## 3.1) Сейчас (после merge ex-2): polish + soak, без этапов 1–2

Этапы **1** (WS UI) и **2** (автономия / колонка) **отложены** — сначала стабильный стенд.

**Порядок сейчас:**

1. Sync docs / prompts / stubs (пути Event Bus, примеры persona, `local_voice` stub).
2. Полировка известного Discord UX (lyrics newlines — BUG-001).
3. Финальный PR → `main`.
4. Soak: ядро + Discord + Lavalink/music ~сутки на Windows → потом локальный mini-PC.
5. Только после soak — возвращаться к этапам 1–2.

---

## 4) Очередь этапов

| # | Этап | Статус |
|---|------|--------|
| **ex-1 / ex-2** | Hub + core layout/refactor + точечные улучшения агента/голоса | ✅ done (архив выше) |
| **polish + soak** | Docs/prompts sync, Discord+music soak (Win → mini-PC) | ▶ **активный** |
| **1** | Web UI как WebSocket-мост к Event Bus | очередь (**позже**, после soak) |
| **2** | Автономный сервер + тонкие клиенты / колонка | очередь (**позже**) |

---

## Этап 1 — Web UI как WebSocket-мост к Event Bus (позже)

**Статус:** отложен до завершения soak Discord+music.

**Зачем до автономии:** UI тестируется на текущем сервере (Discord/API уже есть); колонки как железа пока нет.

**Цель:** браузер = real-time клиент шины — тот же класс тонких клиентов, что позже у колонки (этап 2).

- Двусторонний WS-мост `Web UI ↔ Event Bus`.
- Публикация событий (чат, музыка, плагины) + подписка на stream/статусы.
- Задел под edge/desktop/mobile: тот же WSS-контракт (аудио / текст / события).
- Дашборд (`frontend/`) — развивать как тонкий клиент, не дублируя оркестрацию ядра.

**Критерии приёмки:**

- [ ] CLI не обязателен для повседневной эксплуатации.
- [ ] UI реагирует на операции и события в real-time.
- [ ] Контракт WS задокументирован для переиспользования в этапе 2.
- [ ] (опц.) Vision smoke: картинка в Discord / UI при `use_brain_model_for_vision` true/false.

**Правила:** не ломать Hub / Event Bus без ADR; не тащить self-host voice stack сюда (этап 2). После slice: `compileall` + healthcheck; при касании агента — MCP `/v1/chat` или Discord.

---

## Этап 2 — Автономный сервер + тонкие клиенты

**Ориентир:** после зелёного WS-моста (этап 1). Нет стабильного стенда колонки для приёмки.

Neyra = **один сервер**; колонка / телефон / Web UI = micro-client.

| Узел | Роль |
|------|------|
| **Neyra Server** | ядро, Hub, LLM, STT/TTS (local или cloud), tools, Event Bus |
| **Колонка / edge** | mic/speaker, wake-word; Fast-Path света/сцен локально |
| **Телефон / Web UI** | тонкий клиент по WSS (контракт этапа 1) |

### LLM

- OpenAI-compatible self-host (LM Studio / Ollama / vLLM / …) через профили `base_url` + model id.
- Роли brain / talk / deep / memory / vision — независимо cloud или local.
- Режим «только свой сервер» без обязательного OpenRouter — или слабый сервер → фундамент (OpenRouter и др.).

### Voice (переключаемые STT / TTS)

Один конфиг-переключатель на роль (`voice.stt` / `voice.tts` modality уже в ядре):

| Режим | STT | TTS |
|-------|-----|-----|
| **Local** | Whisper / faster-whisper | CosyVoice / Silero / Piper |
| **Cloud** | Deepgram, Groq, Yandex SpeechKit, … | те же экосистемы |
| **Фундамент** | OpenRouter `/audio/transcriptions` (Whisper turbo — уже в коде); live mic — отдельные live-провайдеры | слот провайдера без ломки агента |

Cloud и local — равноправны. Колонка шлёт аудио на сервер; backend выбирается конфигом.

### Память / vision на сервере

- Hub + Chroma только на сервере.
- Опционально: sqlite-vss через адаптер `search_semantic` (без ломки агента).

### Fast-Path / умный дом (продолжение серверного allowlist)

Серверный allowlist + `home.*` уже в коде. Здесь — e2e с реальными клиентами:

- [ ] Колонка / телефон / desktop home-клиент шлёт короткие команды → Fast-Path без полного brain.
- [ ] Изоляция «ещё раз» между разными клиентами/аккаунтами (не только MCP uid).
- [ ] Consumer `home.*` (свет/сцены) подключён к железу или mock-плагину.

### Критерии приёмки (черновик)

- [ ] STT/TTS: local ↔ cloud только конфигом.
- [ ] Слот STT через OpenRouter задокументирован или работает (база уже есть).
- [ ] Профиль LLM local/custom **или** полный прогон на OpenRouter — оба в example config.
- [ ] Self-host: LLM + STT + TTS без внешних API (при наличии железа); слабый сервер — через cloud.
- [ ] Edge «включи свет» без LLM; сложный запрос — WSS → сервер (когда появится клиент).
- [ ] В колонку не требуется полный репозиторий Neyra.
- [ ] (опц.) Vision smoke на клиенте/колонке.

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
- WS bridge pub/sub (этап 1)
- MCP debug + runtime MCP client
- `scripts/test_stage2_security_offline.py` (scoped archive / ContextVar / 429)

---

## 6) Чек-лист валидации после существенных изменений

- `python -m compileall -q core interfaces scripts main.py` (из `.venv_win` на Windows)
- `python scripts/test_memory_hub_smoke.py` + `test_memory_cutover_offline.py`
- `python scripts/test_stage2_security_offline.py`
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
- **Hub / Event Bus** — контракты не ломать без ADR; регрессии ловить smokes.

---

## 7.5) Баг-трекер / известные дефекты

*Исторический срез логов 2026-05; пути обновлены под раскладку core. Пересмотреть при следующем стресс-прогоне.*

| ID | Суть | Статус | Зона / направление |
|----|------|--------|---------------------|
| **BUG-001** | Discord lyrics: ломаются переносы строк | ⚠️ watch (fix: instruction + unescape `\\n`) | `interfaces/discord/bot.py` + `reply_postprocess` — проверить на soak |
| **BUG-002** | VL Alibaba `DataInspectionFailed` | ❌ open | fallback VL / другой провайдер / смягчение промпта |
| **BUG-003** | Vision free: HTTP 429 | ❌ open | BYOK / другая модель / backoff |
| **BUG-004** | LLM first-token timeout 6s | ⚠️ watch | `primary_first_token_timeout_seconds` |
| **BUG-005** | Discord Gateway reconnect | ⚠️ monitor | сеть / VPN / firewall |
| **BUG-006** | `music.play` failed | ❌ open | санитизация query, Soundcloud; нужен Lavalink на soak |
| **BUG-007** | Частые перезапуски ядра | ❌ open | exit-код / Event Log / repro |
| **BUG-008** | Legacy Chroma docs без `user_id` не попадают в scoped search | ⚠️ watch | переиндексация / backfill metadata; post-filter уже пропускает ambiguous dialog |

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
- Клиенты desktop / mobile-lite — [Google Docs ТЗ](https://docs.google.com/document/d/10wjeJefCRuF1ujJ0bWCwKw2tB9BwjV2ejqqd1f-vMhg/edit?tab=t.0).
- Standalone `.exe` / server-core + lightweight clients.
- Настройка LLM из Web UI (модель, system prompt) — после hot-reload.
- Device-mode (AI station), open-core расширения, публичный demo/BYOK.
- Live mic ASR / realtime WebSocket STT (не file/clip OpenRouter).
