[Cursor AI assist](https://cursor.com)

Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).

---

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
- **Local-first runtime:** cloud-провайдеры опциональны; целевой режим — автономная работа на железе пользователя.
- **MCP-native future:** внешние возможности подключаются стандартизированными MCP-серверами.

---

## 3) Текущее состояние (сводно)

### Стабильные подсистемы

- Режимы `console` / `core`, Plugin Loader и Event Bus стабильны.
- **Internal API** + **дашборд** (React + Vite + Tailwind, `frontend/`) + WebSocket `/v1/ws/` работают.
- Скрипты запуска (`run_neyra.*`), healthcheck и загрузка Lavalink усилены.
- Память многослойная (STM/LTM/PeopleDB/Diary/Reflection); lifecycle LTM и control-plane реализованы.

### Завершённые этапы (кратко)

**Этап A — Discord-контур** ✅
Единый плагин `interfaces/discord/` (text + music), один Discord-клиент, Lavalink 4.x, YouTube-обход (ANDROID_VR).

**Этап B — Контекст, память, безопасность** ✅

- B1: Speaker ID Injection (PeopleDB, `_resolve_speaker_label`).
- B2: Динамическое взвешивание памяти (`_build_system_prompt`, 6 секций).
- B3: LTM lifecycle (`core/ltm_maintenance.py`, TTL prune, cold archive, API endpoints).
- B4: Security (ролевая модель, HMAC webhooks, rate limiting).
- B5: Proactive Messaging (Discord, только в плагине).

**Этап E1 — MCP debug server** ✅
`tools/mcp_server/` (stdio MCP: логи, API, fire_event, конфиг, память). Dockerfile + docker-compose.yml в корне.

**Этап E2 — MCP-клиент** ✅
`core/mcp_client.py` (MCPClientManager, stdio + SSE, динамические LangChain tools, tool-loop на brain-модели).

**Этап F — Brain→Talk, 4 роли моделей** ✅

- 4 роли: talk / brain / memory / vision.
- Вложенный `openrouter` (talk_model, brain_model, memory_model, vision_model).
- VL pipeline: caption → brain tool-loop → talk stream.
- Legacy fallback (старые ключи `openrouter.model` и др.) с warning в лог.

---

## 4) Очередь этапов (обновлено)

**Порядок реализации:**

1. **E3** — Безопасное самопрограммирование + hot-reload (фундамент для всех плагинов)
2. **D** — Полная локальная автономность (Voice + Runtime)
3. **C** — Web UI как WebSocket-мост (оставлен на конец, после стабилизации плагинов)

---

## Этап E3 — Безопасное самопрограммирование + hot-reload + rollback

**Цель:** расширить MCP-архитектуру средствами безопасного обновления плагинов. **Делаем в самое начало — фундамент для всех плагинов.**

### Механика ядра (Core Machinery)

Механизм перезагрузки живёт нативно в ядре. В `core/plugin_loader.py` планируется добавить методы:

- **`reload_plugin(plugin_id)`** — для безопасной остановки плагина, очистки его подписок в Event Bus и повторной загрузки «на горячую» без остановки `core`.
- **`rollback_plugin(plugin_id)`** — для отката файлов плагина из бэкапа в случае критической ошибки (`Exception`) при загрузке.

### Нативный инструмент (Builder Tool)

Для модели-маршрутизатора (**brain_model**) будет создан нативный MCP-совместимый инструмент (например, `create_or_edit_plugin`).

Инструмент работает как интерфейс к внешней/специализированной LLM для программирования (Sub-agent), которая генерирует код, после чего инструмент сохраняет файлы и вызывает `reload_plugin`.

### Жёсткий Sandbox и безопасность (внутри инструмента)

**Тюрьма путей (Path Jail):**
Инструмент обязан проверять пути через `os.path.abspath` и разрешать запись **СТРОГО** внутри директории `interfaces/`. Любые попытки выхода (Path Traversal вида `../core/`) должны блокироваться.

**Чёрный список (Blacklist):**
Инструмент должен аппаратно блокировать любые изменения в критически важных плагинах:

```
["discord", "internal_api", "laptop_screen"]
```

При попытке их изменить инструмент возвращает ошибку доступа.

**Делегирование (Личный кодер):**
Инструмент не пишет код сам — он делегирует генерацию внешней LLM (Sub-agent), сохраняет результат и инициирует hot-reload через ядро.

### Чек-лист реализации

- [ ] **Sandbox policy:**
  - [ ] Разрешить self-coding только в `interfaces/`.
  - [ ] Запретить модификации `core/` автоматическими агентными операциями.
- [ ] **Механика ядра (core/plugin_loader.py):**
  - [ ] `reload_plugin(plugin_id)` — stop, cleanup Event Bus subscriptions, re-import.
  - [ ] `rollback_plugin(plugin_id)` — restore from backup on critical Exception.
- [ ] **Нативный инструмент (brain_model):**
  - [ ] `create_or_edit_plugin` (MCP-compatible).
  - [ ] Path Jail: `os.path.abspath`, strict `interfaces/` only, block `../core/`.
  - [ ] Blacklist: block edits for `["discord", "internal_api", "laptop_screen"]`, return access error.
  - [ ] Делегирование: внешний LLM/Sub-agent генерирует изменения; инструмент сохраняет файлы и вызывает `reload_plugin`.
- [ ] **Hot-reload плагинов:**
  - [ ] Обновление кода/конфигов и обработчиков Event Bus без остановки `core`.
- [ ] **Rollback:**
  - [ ] Откат файлов плагина при критической ошибке загрузки.

**Критерии приемки:**

- [ ] Самопрограммирование ограничено sandbox-границами (`interfaces/` only).
- [ ] Hot-reload/rollback воспроизводимы в тестах.
- [ ] Path Traversal блокируется на уровне инструмента.
- [ ] Чёрный список плагинов невозможно модифицировать через агента.

---

## Этап D — Полная локальная автономность (Voice + Runtime)

**Цель:** 100% автономная работа системы на железе пользователя без интернета. **Второй по списку.**

### D — Локальный Voice Stack (не выполнено)

- **Локальный STT:** Whisper / faster-whisper в `local_voice`.
- **Локальный TTS (GPU):** CosyVoice 3.0 (Zero-shot Voice Cloning, эмоции).
- **Локальный TTS (CPU):** Silero TTS или Piper TTS.
- Облачные STT/TTS (Deepgram/Yandex) как fallback.

### D — Автономный стек (не выполнено)

- Local LLM + Local STT + Local TTS + локальная память.
- Доработать `laptop_screen` под безопасный локальный screen/vision pipeline.

**Критерии приемки:**

- Основные сценарии работы агента доступны в оффлайн-режиме.
- Voice pipeline переключается между ресурсоёмкими и легковесными движками.

### D1 — Docker (базовый контур выполнен)

- Dockerfile + docker-compose.yml (порты `8787`, тома для `config.yaml`, `interfaces/`, `memory/`, `logs/`).
- Решение "переходим ли на Docker" (приоритет — Windows one-click `run_neyra.bat` или Linux CI).

---

## Этап C — Web UI как WebSocket-мост к Event Bus

**Цель:** сделать браузер нативным real-time клиентом шины событий. **Делаем самым последним.**

- Реализовать двусторонний WS-мост `Web UI <-> Event Bus`.
- Браузер публикует события напрямую (чат, музыка, плагины).
- Браузер подписывается на stream-ответы и статусные события.
- Управление плагинами и чатом в едином transport-контуре.

**Критерии приемки:**

- CLI не обязателен для повседневной эксплуатации.
- Реакция UI на операции/события идет в real-time.

---

## 5) Архитектурные артефакты (не выполнено)

- **ADR-документы:**
  - Единый `discord` плагин.
  - Memory lifecycle policy.
  - MCP integration model.
  - Sandbox/hot-reload/rollback policy.
- **Тестовые сценарии:**
  - e2e Discord text+music.
  - Memory prune/summarize flows.
  - WS bridge pub/sub.
  - MCP debug and client connectivity.

---

## 6) Чек-лист валидации после существенных изменений

- Backend compile: `python -m compileall -q core interfaces scripts main.py`
- Frontend build: `cd frontend && npm run build`
- Core healthcheck: `python scripts/healthcheck.py --mode core --skip-http`
- Lavalink JAR: `python scripts/fetch_lavalink.py`
- Event-driven smoke: chat → MUSIC_PLAY → queue → skip/pause/resume → stop/clear
- Memory lifecycle smoke: write → search → prune → summarize → archive integrity
- MCP smoke: debug-server tools + runtime MCP client calls

---

## 7) Риски и контроль

- Риск: деградация качества при автоматическом prune/summarize.
  - Контроль: quality gates и выборочные проверки retrieval.
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

## 7.6) Legacy и fallback (этап F+)

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
- `interfaces/laptop_screen/` — заглушка, не связана с текущим `vision_model`.

---

## 8) Backlog (дальний горизонт)

- **Интеграция с Obsidian** — экспорт LTM/Diary/PeopleDB в vault как `.md` (через MCP или Python CLI).
- Desktop и mobile-lite клиенты.
- Standalone `.exe` сборка / `server-core + lightweight clients`.
- **Настройка LLM из Web UI** (выбор модели, правка system prompt) — после hot-reload.
- Device-mode (AI station).
- Open-core модель расширений.
- Публичный demo/BYOK режим.

