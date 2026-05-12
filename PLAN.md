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

### Завершённые работы (кратко)

**Discord-контур** ✅  
Единый плагин `interfaces/discord/` (text + music), один Discord-клиент, Lavalink 4.x, YouTube-обход (ANDROID_VR).

**Контекст, память, безопасность** ✅

- Speaker ID Injection (PeopleDB, `_resolve_speaker_label`).
- Динамическое взвешивание памяти (`_build_system_prompt`, 6 секций).
- LTM lifecycle (`core/ltm_maintenance.py`, TTL prune, cold archive, API endpoints).
- **Консолидация LTM во «сне»:** кластеризация старых записей по косинусной близости эмбеддингов (`memory.ltm_cluster_merge`), несколько вызовов `memory_model` на кластер, JSON-манифесты батча в `memory/ltm_consolidation/`, в Chroma удаляются только строки успешно заархивированных кластеров; опционально запуск summarize после ночной рефлексии (`ltm_auto_summarize.run_after_nightly_reflection`). В `core/memory.py`: `encode_texts`, `archive_row_tuples`.
- **Working memory (1–3 дня):** `core/working_memory.py` + `memory.working_memory`; markdown на пользователя (`storage_dir`) или общий файл; перепись через **`openrouter.memory_model`**; блок в промпте **до RAG** (talk + brain); фоновое обновление после успешного `chat`/`chat_stream` (каждые N ходов и при переполнении контекста); шина `memory.working_memory_updated`.
- **Эмоциональный слой:** `core/emotional_layer.py` + `memory.emotional_layer`; после хода — запись в дневник (`emotion_turn`, **memory_model**); опционально **`ltm_emotion_sync`** — метаданные `assistant_emotion` в Chroma при сохранении диалога; PeopleDB `dynamic_facts[].emotion`; инструменты `remember_knowledge(..., affect_note)`, `update_person_fact(..., emotion_note)`; `NeyraDiary.recent_text` показывает `настр.` из `meta`.
- Security (ролевая модель, HMAC webhooks, rate limiting).
- Proactive Messaging (Discord, только в плагине).

**MCP debug server** ✅  
`tools/mcp_server/` (stdio MCP: логи, API, fire_event, конфиг, память). Dockerfile + docker-compose.yml в корне.

**MCP-клиент** ✅  
`core/mcp_client.py` (MCPClientManager, stdio + SSE, динамические LangChain tools, tool-loop на brain-модели).

**Brain→Talk, четыре роли моделей** ✅

- Роли: talk / brain / memory / vision; вложенный `openrouter` и отдельные id моделей.
- VL pipeline: caption → brain tool-loop → talk stream.
- Legacy fallback (старые ключи `openrouter.model` и др.) с warning в лог.

**Безопасное самопрограммирование плагинов (sandbox, hot-reload, rollback)** ✅

- `core/plugin_loader.py`: файловые бэкапы в `memory/plugin_backups/`, `reload_plugin`, `rollback_plugin`.
- Инструмент `create_or_edit_plugin` (`core/tools.py` → `core/plugin_builder_tool.py`): path jail только внутри `interfaces/`, blacklist критичных плагинов, генерация кода через внешнюю LLM (OpenRouter), откат при сбое загрузки.

*Примечание:* для resident-плагинов, уже запущенных в своём потоке, полный lifecycle stop/start по-прежнему отдельная задача; re-import покрывает CLI/invoke и будущие вызовы.

---

## 4) Очередь этапов

Этап **1** — дальше точечные улучшения; этапы **2–3** зафиксированы в конце очереди.

**Порядок реализации:**

1. **Этап 1** — Дополнительные точечные улучшения (персона, pre-context, безопасность, архив сессии).
2. **Этап 2** — Полная локальная автономность (Voice + Runtime).
3. **Этап 3** — Web UI как WebSocket-мост к Event Bus.

---

## Этап 1 — Дополнительные улучшения (пакет мелких задач)

Сделать по мере необходимости; можно распараллелить:

- **Pre-context «мысли»:** короткий релевантный блок из дневника перед основным ответом (формализовать поверх текущего RAG + PeopleDB).
- **Персона в двух артефактах:** разделить «базу личности» и «внешность / визуал» (актуально при генерации изображений или отдельном визуальном контуре); редактируемые файлы рядом с `assistant.system_prompt`.
- **Контролируемое архивирование сессии:** при переполнении контекста — явная политика дампа в Diary/LTM и «чистый» старт диалога (не обязательно фиксированный порог токенов).
- **Сверка практик безопасности:** не светить секреты, риски смешения данных между людьми — перекрёстно с `security-model.md` и документацией деплоя.

---

## Этап 2 — Полная локальная автономность (Voice + Runtime)

**Цель:** устойчивая работа системы на железе пользователя без обязательного интернета.

### Локальный Voice Stack (не выполнено)

- **Локальный STT:** Whisper / faster-whisper в `local_voice`.
- **Локальный TTS (GPU):** CosyVoice 3.0 (Zero-shot Voice Cloning, эмоции).
- **Локальный TTS (CPU):** Silero TTS или Piper TTS.
- Облачные STT/TTS (Deepgram/Yandex) как fallback.

### Автономный стек (не выполнено)

- Local LLM + Local STT + Local TTS + локальная память.
- Доработать `laptop_screen` под безопасный локальный screen/vision pipeline.

**Критерии приёмки:**

- Основные сценарии агента доступны в оффлайн-режиме.
- Voice pipeline переключается между ресурсоёмкими и легковесными движками.

### Docker (базовый контур выполнен)

- Dockerfile + docker-compose.yml (порты `8787`, тома для `config.yaml`, `interfaces/`, `memory/`, `logs/`).
- Решение приоритета: Windows one-click `run_neyra.bat` vs Linux CI/Docker.

---

## Этап 3 — Web UI как WebSocket-мост к Event Bus

**Цель:** браузер как полноценный real-time клиент шины событий (после стабилизации плагинов и очереди выше).

- Двусторонний WS-мост `Web UI <-> Event Bus`.
- Браузер публикует события (чат, музыка, плагины) и подписывается на stream-ответы и статусы.
- Управление плагинами и чатом в одном transport-контуре.

**Критерии приёмки:**

- CLI не обязателен для повседневной эксплуатации.
- Реакция UI на операции и события в real-time.

---

## 5) Архитектурные артефакты (не выполнено)

- **ADR-документы:**
  - Единый `discord` плагин.
  - Memory lifecycle policy.
  - MCP integration model.
  - Sandbox/hot-reload/rollback policy.
- **Тестовые сценарии:**
  - e2e Discord text+music.
  - Memory prune/summarize flows (включая dry-run и ветку `cluster_merge` у summarize); working memory (вкл. в конфиге, пару ходов чата, проверка файла и промпта); emotional_layer (дневник `emotion_turn`, опционально `ltm_emotion_sync`).
  - WS bridge pub/sub.
  - MCP debug and client connectivity.

---

## 6) Чек-лист валидации после существенных изменений

- Backend compile: `python -m compileall -q core interfaces scripts main.py`
- Frontend build: `cd frontend && npm run build`
- Core healthcheck: `python scripts/healthcheck.py --mode core --skip-http`
- Lavalink JAR: `python scripts/fetch_lavalink.py`
- Event-driven smoke: chat → MUSIC_PLAY → queue → skip/pause/resume → stop/clear
- Memory lifecycle smoke: write → search → prune → summarize → archive integrity; emotional_layer (вкл., дневник + PeopleDB tool с emotion_note)
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
- `interfaces/laptop_screen/` — заглушка, не связана с текущим `vision_model`.

---

## 8) Backlog (дальний горизонт)

- **Интеграция с Obsidian** — экспорт LTM/Diary/PeopleDB в vault как `.md` (через MCP или Python CLI).
- **Полировка и чистка мусора по всему проекту** — пройтись по репозиторию повторно: убрать временные файлы/артефакты тестов, выровнять стили, привести конфиги/доки в порядок, зачистить устаревшие ветки fallback и лишние логи.
- Desktop и mobile-lite клиенты.
- Standalone `.exe` сборка / `server-core + lightweight clients`.
- **Настройка LLM из Web UI** (выбор модели, правка system prompt) — после hot-reload.
- Device-mode (AI station).
- Open-core модель расширений.
- Публичный demo/BYOK режим.
