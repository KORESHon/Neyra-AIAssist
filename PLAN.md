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
- **Plugin-first:** интерфейсная логика живет в `interfaces/`*, ядро остается универсальным.
- **Secure-by-boundary:** `core` защищен от прямой саморедактируемости; расширения делаются через sandbox в плагинной зоне.
- **Local-first runtime:** cloud-провайдеры опциональны; целевой режим — автономная работа на железе пользователя.
- **MCP-native future:** внешние возможности подключаются стандартизированными MCP-серверами.

---

## 3) Текущее состояние (сводно)

- Режимы `console` / `core`, Plugin Loader и Event Bus стабильны.
- **Internal API** + **дашборд** (React + Vite + Tailwind, `frontend/`) + WebSocket `/v1/ws/`* работают; до этапа C основной контур UI — HTTP `/v1`.
- **Этап A завершён:** единый плагин `interfaces/discord/` (текст + музыка), один Discord-клиент, музыка через Lavalink 4.x и актуальные source-плагины / клиенты (в т.ч. обход ограничений YouTube, например ANDROID_VR там, где требуется).
- **Этап E1 (базовый MCP debug + DX в Docker) выполнен:** `tools/mcp_server` (stdio MCP: логи, HTTP к API, `neyra_health`, опционально `neyra_lifecycle` при включённом lifecycle, fire_event, конфиг, память); в корне — `Dockerfile` + `docker-compose.yml` (проброс `8787`, `INTERNAL_API_BIND_HOST=0.0.0.0`, тома для `config.yaml`, `interfaces/`, `memory/`, `logs/`, опционально `frontend/dist`).
- **Этап E2 (базовая интеграция MCP-клиента) выполнена:** `core/mcp_client.py` (`MCPClientManager` — stdio + SSE, `list_tools` → LangChain tools с именами `mcp_<server>_<tool>`, `call_tool`), конфиг `mcp_client` в `config.yaml`; агент подмешивает MCP-tools после `start_mcp_clients`, маршрутизация через `_execute_tool`; опционально `llm_tool_calls` — цикл на **brain**-модели (этап F). Дальше — политики безопасности и прочее. **E3** (sandbox/hot-reload) — впереди.
- **Этап F выполнен** (пайплайн Brain→Talk, четыре роли моделей, вложенный `openrouter`, единый `vision_model`): см. **«Этап F»** ниже и `New.md` в корне репозитория.
- Память многослойная (STM/LTM/PeopleDB/Diary/Reflection); **lifecycle LTM и control-plane** — в этапе B.
- Скрипты запуска (`run_neyra.`*), healthcheck и загрузка Lavalink усилены.

---

## 4) Stage-gated roadmap

## Этап A — Discord-контур и стабилизация рантайма

**Цель:** устранить архитектурный долг в Discord-интеграции и завершить стабилизацию музыки.

- ~~Слить `discord_text` и `discord_music` в единый плагин `discord`.~~ **Сделано:** resident-плагин `interfaces/discord/` (`bot.py` + `music.py`), старые плагины удалены.
- ~~Использовать один инстанс Discord-клиента для всей гильдии.~~ **Сделано:** клиент поднимается один раз в `interfaces/discord/bot.py`.
- ~~Внутри плагина выделить подмодули (`text` и `music`) как Cogs/сервисы.~~ **Сделано:** разделение `bot.py` (text/gateway) и `music.py` (music service + Lavalink adapter).
- ~~**Критично:** даже внутри единого плагина взаимодействие модулей оставлять через Event Bus (`MUSIC_PLAY` и прочие `MUSIC`_*), а не прямыми вызовами.~~ **Сделано:** Discord-модуль публикует/слушает только `MUSIC`_* события.
- ~~Устранить текущие edge-cases playback/search/queue.~~ **Сделано:** добавлены failover, timeout/pending, безопасные queue embeds и пагинация.
- ~~Зафиксировать backward-compatible формат payload/result для MUSIC-событий.~~ **Сделано:** результат нормализован для event/invoke и публикуется через `MUSIC_RESULT`.

**Критерии приемки:**

- В рантайме отсутствует дублирование Discord-клиентов.
- Модуль `music` стабильно обрабатывает play/queue/skip/pause/resume/stop.
- Нет деградации API/UI, использующих MUSIC-события.

**Статус этапа A: завершён.** 

## Этап B — Контекст, память и безопасность control-plane

**Цель:** исправить путаницу пользователей в групповых чатах и сделать память управляемой.

### B1. Многопользовательский контекст (Speaker ID Injection) — **сделано**

- Единый формат реплик в STM и в **текущем** HumanMessage: `[Пользователь {метка}]: …` (метка = PeopleDB при наличии, иначе отображаемое имя Discord / логин).
- `core/agent.py`: `_resolve_speaker_label`, `_format_spoken_user_message`, префикс в `_make_human_turn` (включая VL-текст в мультимодальном сообщении).
- Discord: на каждый ход передаются `username` (`author.name`) и `author_display_name` (nick / global_name / name).
- Internal API: `POST /v1/chat` — поле `author_display_name`; webhook inbound — `author_display_name` / `display_name`; WS — те же ключи в JSON.

*(LangChain не использует нативное поле `name` у HumanMessage для всех провайдеров; текстовый префикс — переносимый контракт.)*

### B2. Динамическое взвешивание памяти (Context Weighting) — **закрыт**

Порядок секций в `_build_system_prompt` (сверху вниз — так модель читает системный контекст):

1. **Базовая роль** — `assistant.system_prompt` + примечание о типе LLM endpoint + `[ВРЕМЯ И СРЕДА]` (дата/время без имени; имя только в блоке активного).
2. **Активный собеседник** — строка «с кем диалог» + досье PeopleDB текущего пользователя (если есть).
3. **Упомянутые люди** — остальные досье + `[ПРИОРИТЕТ ДОСЬЕ]` при двух блоках.
4. **Правила поведения и стиль** — критическое правило ответа, анти-повтор, опционально микропланирование.
5. **Долгосрочная память (RAG)** — фрагменты прошлых разговоров.
6. **Дополнительно по запросу хода** — личный дневник Нейры → данные из интернета → результаты инструментов → (в хвосте) зрение / последний скрин / режим текста песни.

Реализация: `_split_people_context_for_prompt`, `_shrink_people_sections` при retry после переполнения контекста; одинаково в `chat` и `chat_stream`.

### B3. Жизненный цикл LongTermMemory (ChromaDB) — **закрыт**

Трехшаговая стратегия:

1. **TTL + Prune-job**
  - TTL для низкоприоритетных/фоновых диалогов,
  - фоновая регулярная очистка.
2. **Summarization -> Cold Archive**
  - старые записи сжимаются в summary-документы,
  - оригиналы уводятся в архив (cold storage).
3. **Операционное API**
  - endpoint-ы обслуживания памяти из dashboard:
    - ~~`/v1/memory/prune`~~ **Сделано:** TTL-подобная очистка по `timestamp` в метаданных Chroma.
    - ~~`/v1/memory/summarize`~~ **Сделано:** cold archive (JSONL) + опционально digest через LLM (`type=ltm_digest` в RAG).
    - ~~`/v1/memory/policies`~~ **Сделано:** GET сводки политик из конфига (в т.ч. расписание авто-джобов).
    - ~~`/v1/memory/reindex`~~ **Сделано:** операционная проверка индекса (Chroma persistent; без массовой переэмбеддинга).

**Фон:** `memory.ltm_auto_prune` и `memory.ltm_auto_summarize` — интервальные джобы в **APScheduler** рядом с рефлексией (`core/reflection.py`), логика — `core/ltm_maintenance.py`. Дашборд: блок обслуживания памяти на главной странице UI.

### B4. Security hardening — **закрыт**

- ~~Ролевая модель и аудит критичных API-операций.~~ **Сделано:** уровни токена `admin` / `maint` / `viewer` (`INTERNAL_API`_* в `.env`), расширенный аудит (лог + **JSONL** `internal_api.audit_log_path`, события: память, notify, плагины, webhooks, debug/fire_event, backup, config).
- ~~Усиление webhook подписи/верификации.~~ **Сделано:** опциональный HMAC для `POST /v1/webhooks/in/...` (`WEBHOOK_INBOUND_SECRET` / `webhook_inbound_secret`).
- ~~Rate limiting и anti-abuse.~~ **Сделано:** опциональный лимит RPM по IP для `/v1` (`rate_limit_requests_per_minute`, WS исключён).

### B5. Спонтанная активность (Proactive Messaging) — **закрыт**

**Идея:** Нейра должна периодически сама писать в активный канал (раз в 10–30 минут с рандомизацией), вкидывая свежие мемы, новости или комментируя тишину.

**Строгое архитектурное правило:** для этой фичи **не изменяем ядро** (`core/`).

**Реализация:** логика **только** в `interfaces/discord/bot.py`: `discord.ext.tasks.loop`, случайная пауза между итерациями (`discord.proactive.min/max_interval_minutes`), запрос к `**POST /v1/chat`** (тот же контракт, что у дашборда), публикация текста в канал. Конфиг: `interfaces/discord/config.yaml` → блок `**discord.proactive`** (вкл/выкл, канал, таймаут, опционально свой `prompt`).

**Критерии приемки:**

- Нейра корректно различает собеседников в групповых чатах.
- Контекст активного собеседника стабильно доминирует в prompt.
- Размер LTM контролируем, есть штатные операции обслуживания.
- Критичные API защищены.
- ~~Проактивные сообщения Discord (B5) реализуются только в плагине, без изменений `core/`; вызов модели — через Internal API (`POST /v1/chat`).~~ **Сделано.**

## Этап C — Web UI как WebSocket-мост к Event Bus

**Цель:** сделать браузер нативным real-time клиентом шины событий.

- Реализовать двусторонний WS-мост `Web UI <-> Event Bus`.
- Браузер публикует события напрямую:
  - чат-команды,
  - управление музыкой,
  - plugin operations.
- Браузер подписывается на stream-ответы и статусные события.
- Управление плагинами и чатом работает в едином transport-контуре.

**Критерии приемки:**

- CLI не обязателен для повседневной эксплуатации.
- Реакция UI на операции/события идет в real-time.

## Этап D — Полная локальная автономность (Voice + Runtime)

Цель: 100% автономная работа системы на железе пользователя без интернета.

- `local_voice` получает нативную поддержку модульного локального аудио-стека:
  - **Локальный STT:** Whisper / faster-whisper.
  - **Локальный TTS (High-end GPU):** Интеграция CosyVoice 3.0 (Zero-shot Voice Cloning, потоковая передача, instruct-управление эмоциями) для пользователей с дискретными видеокартами.
  - **Локальный TTS (CPU-friendly):** Silero TTS или Piper TTS для работы в реальном времени на слабых машинах и мини-ПК без GPU.
  - Облачные STT/TTS (Deepgram/Yandex) остаются как опциональный fallback, а не обязательность.
- Поддержать целевой автономный стек: Local LLM + Local STT + Local TTS + локальная память.
- Доработать `laptop_screen` под безопасный локальный screen/vision pipeline (обработка экрана без утечки данных в облако).

Критерии приемки:

- Основные сценарии работы агента доступны в оффлайн-режиме.
- Voice pipeline работоспособен без внешних API и может переключаться между ресурсоемкими (CosyVoice) и легковесными (Silero/Piper) движками через конфигурацию.

### D1. Docker / контейнеризация (оценка на этапе D, без обязательного внедрения)

**Зачем Docker для Нейры**

- Воспроизводимое окружение (Python, Java, системные либы) на другой машине или CI.
- Изоляция портов (`8787`, Lavalink `2333`), проще поднять несколько инстансов на одном хосте с разными compose-проектами.

**Минусы и ограничения**

- **Плагины без нового билда:** если в образ **копируются** `interfaces/` на этапе `docker build`, любое изменение плагина = пересборка. Чтобы обновлять плагины без rebuild, нужен **bind mount** тома на хост (`./interfaces:/app/interfaces`) или отдельный образ только для «тонкого» рантайма.
- **Данные:** `memory/`, `config.yaml`, логи, Chroma — должны жить на **named volume** или bind mount, иначе контейнер stateless и память «пропадает» при удалении контейнера.
- **Lavalink:** отдельный сервис в compose проще сопровождать, чем один «толстый» контейнер; версии JAR и `application.yml` всё равно нужно синхронизировать с `discord.music.nodes`.
- **GPU (CosyVoice / Whisper и т.д.):** нужен runtime NVIDIA (`nvidia-container-toolkit`), иначе в Docker только CPU — это отдельная сложность этапа D.
- **Отладка:** stack trace и live reload удобнее на хосте; в Docker полезны healthcheck + логирование в volume.

**Вывод для плана D**

- Полная «упаковка в Docker» возможна как **compose**: `core` + `lavalink` + опционально `frontend` build, с томами для `interfaces/`, `memory/`, `.env`.
- Решение «переходим ли на Docker в D» принимается отдельно: если приоритет — **домашний one-click на Windows**, текущие `run_neyra.`* + venv могут остаться основным путём, а Docker — для Linux-сервера/CI.

## Этап E — MCP-архитектура

**Цель:** перевести интеграции и DX на стандарт Model Context Protocol.

### E1. Вектор Developer Experience: `neyra-mcp-debug-server` — **базовая поставка выполнена**

Реализовано в репозитории (`tools/mcp_server`, FastMCP + httpx):

- чтение хвоста системного лога (`read_neyra_logs`);
- универсальные вызовы Internal API (`neyra_api_request`);
- быстрый ping ядра (`neyra_health` → `GET /v1/health`);
- инъекция событий в шину через `POST /v1/debug/fire_event` (`neyra_fire_event`);
- безопасное чтение корневого `config.yaml` с редакцией секретов (`neyra_read_config`);
- точечные обновления через `POST /v1/config/update` (`neyra_write_config`);
- снимок STM/stats/RAG через `GET /v1/debug/memory` (`neyra_inspect_memory`);
- опционально: завершение процесса ядра из MCP (`neyra_lifecycle` → `POST /v1/debug/lifecycle`) при `internal_api.debug_lifecycle_enabled` или `NEYRA_DEBUG_LIFECYCLE=1` и **admin**-токене; «restart» внутри процесса не отличается от «stop» — повторный подъём даёт Docker (`restart: unless-stopped`) или ручной `docker compose restart`.

**Docker Desktop:** `docker compose up --build` из корня; MCP на хосте указывает `NEYRA_API_BASE=http://127.0.0.1:8787`. Логи на хосте доступны агенту, если репозиторий открыт там же, где лежит примонтированный `./logs` (или задайте `NEYRA_LOG_PATH`).

**Остаётся по желанию:** расширенные диагностики, отдельный compose под Lavalink — без блокировки этапов B/C.

### E2. Вектор Runtime: Нейра как MCP-клиент — **базовая интеграция выполнена**

Реализовано:

- `**core/mcp_client.MCPClientManager`:** конфиг `mcp_client.servers` (stdio: `command` + `args`, SSE: строка URL или `url:`), асинхронные сессии MCP SDK, переподключение при падении процесса, `call_tool` / сериализация результата для LLM.
- `**NeyraAgent`:** после `start_mcp_clients()` динамические инструменты добавляются в `self.tools`; `chat()` / `chat_stream()` вызывают `_ensure_mcp()`, опционально `inject_tool_catalog`; при `**mcp_client.llm_tool_calls`** цикл `**bind_tools`** выполняется на `**llm_brain`** (этап F), затем ответ пользователю стримится/генерируется через `**llm_talk**` без инструментов.
- **Запуск:** `start_mcp_clients` из startup FastAPI и из консольного режима `main.py`; `stop_mcp_clients` на shutdown API.

**Дальше по продукту (не блокер E2):** явные политики доступа по серверам, стриминг с tool-loop, catalog ресурсов MCP.

### E3. Безопасное самопрограммирование + hot-reload + rollback

- **Sandbox policy:**
  - разрешить self-coding только в `interfaces/`,
  - запретить модификации `core/` автоматическими агентными операциями.
- **Hot-reload плагинов:**
  - обновление конфигов, обработчиков Event Bus и runtime-состояния без полной остановки `core`.
- **Rollback:**
  - откат версии плагина при критической ошибке загрузки/инициализации.

**Критерии приемки:**

- MCP debug-сервер покрывает ключевые dev-операции (**базовый контур E1 выполнен**; расширения — опционально).
- Подключение внешних MCP-серверов через `mcp_client` (**базовый контур E2**); тонкая настройка интеграций в плагинах — по мере необходимости.
- Самопрограммирование ограничено sandbox-границами.
- Hot-reload/rollback воспроизводимы в тестах.

---

## Этап F — Supervisor Brain→Talk и единая схема моделей (**выполнено**)

**Цель:** разделить финальный ответ пользователю и служебный маршрутизатор с инструментами; завести четыре идентификатора моделей и один контур vision без дублирования YAML.

### Что сделано и где


| Часть                                                                                                                                       | Где в коде / конфиге                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Пайплайн **VL caption → brain (tool-loop / MCP) → talk (стрим, без tools)**                                                                 | `core/agent.py`: `_caption_vision_images`, `_run_brain_tool_phase`, `chat` / `chat_stream`; `bind_tools` на `llm_brain`; вспомогательные регенерации на `llm_talk`.                                                                 |
| Четыре роли: **talk / brain / memory / vision (VL)**                                                                                        | `core/agent.py` (`llm_talk`, `llm_brain`, `llm_memory`, `llm_vision`); `self.llm_primary` = talk для совместимости.                                                                                                                 |
| Резолв имён и разворот вложенных блоков `**talk_model` / `brain_model` / `memory_model` / `vision_model`**                                  | `core/llm_profile.py`: `resolved_*_model`, `expand_openrouter_nested`, `merge_llm_tuning_options`.                                                                                                                                  |
| Единый контур зрения: только `**openrouter.vision_model`** (модель + лимиты + `enabled`, Discord-лимиты картинок, память последнего скрина) | `merged_vision_pipeline`, `resolved_vision_model_id`; агент — `_vision_pipeline_cfg()`; `interfaces/discord/bot.py`. Корневой `**vision:`** в шаблонах удалён; при наличии в старых конфигах подмешивается с предупреждением в лог. |
| Память и рефлексия на **memory_model**                                                                                                      | `core/reflection.py`, `summarize_ltm_corpus`, async reflection; блок `**async_reflection`** без отдельного `model`.                                                                                                                 |
| Секрет screen proxy                                                                                                                         | `core/secrets_loader.py` → `screen_proxy_plugin` (не `vision.screen_proxy`).                                                                                                                                                        |
| Internal API allowlist новых путей                                                                                                          | `interfaces/internal_api/api_server.py` (`/v1/config/update`).                                                                                                                                                                      |
| Discord `/stats`                                                                                                                            | `interfaces/discord/bot.py` (Talk / Brain / Memory).                                                                                                                                                                                |
| Шаблоны конфигов                                                                                                                            | `config.example.yaml`, `config.yaml` пользователя.                                                                                                                                                                                  |


**Заметка:** дашборд (`frontend/src/pages/SettingsPage.tsx`) обновлён на пути `**openrouter.talk_model.model`** (вместо устаревшего только `openrouter.model`).

---

## 5) Архитектурные артефакты, обязательные к поставке

- Обновленные event-контракты и схемы payload/result.
- ADR-документы:
  - единый `discord` плагин,
  - memory lifecycle policy,
  - MCP integration model,
  - sandbox/hot-reload/rollback policy.
- Тестовые сценарии:
  - e2e Discord text+music,
  - memory prune/summarize flows,
  - WS bridge pub/sub,
  - MCP debug and client connectivity.

---

## 6) Чек-лист валидации после существенных изменений

- Backend compile:
  - `python -m compileall -q core interfaces scripts main.py`
- Frontend build:
  - `cd frontend && npm run build`
- Core healthcheck:
  - `python scripts/healthcheck.py --mode core --skip-http`
- Lavalink JAR (если в репо pointer / малый файл):
  - `python scripts/fetch_lavalink.py`
- Event-driven smoke:
  - chat -> MUSIC_PLAY -> queue -> skip/pause/resume -> stop/clear
- Memory lifecycle smoke:
  - write -> search -> prune -> summarize -> archive integrity
- MCP smoke:
  - debug-server tools + runtime MCP client calls

---

## 7) Риски и контроль

- Риск: регресс после слияния Discord-модулей.
  - Контроль: staged rollout + e2e regression suite.
- Риск: деградация качества при автоматическом prune/summarize.
  - Контроль: quality gates и выборочные проверки retrieval.
- Риск: расширение атакующей поверхности через MCP.
  - Контроль: allowlist серверов, sandbox-права, аудит действий.
- Риск: hot-reload может оставлять «грязное» состояние подписок.
  - Контроль: lifecycle hooks + обязательная очистка/перерегистрация listeners.

---

## 7.5) Баг-трекер / известные дефекты

*Обновлено по анализу `logs/system.log` после ночного стресса (2026-05-02 … 2026-05-03).*

- **Зона:** `interfaces/discord/bot.py` (стрим, превью, чанки) + `core/agent.py` (постобработка после стрима).
- **Уже пробовали:** `lyrics_mode`, `lyrics_reply_max_tokens`, сохранение `\n` в `_extract_sound_tags`, блок в системном промпте.
- **Статус:** открыт.

### BUG-002 — VL (vision): Alibaba `DataInspectionFailed` / «inappropriate content»

- **Лог:** `Ошибка стриминга LLM: Upstream error from Alibaba: <400> InternalError.Algo.DataInspectionFailed: Input text data may contain inappropriate content` при VL-ходах (`Зрение: VL-ход`).
- **Интерпретация:** модерация/фильтр на стороне провайдера (не код Нейры); возможны ложные срабатывания на контент изображения или сопутствующего текста.
- **Направление:** fallback VL-модель, смягчение промпта, или другой vision-провайдер через OpenRouter.

### BUG-003 — Vision (free): HTTP 429 и rate limit провайдера

- **Лог:** `Error code: 429` — `google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream` (Google AI Studio через OpenRouter).
- **Интерпретация:** лимиты бесплатной модели; ретраи OpenRouter видны в логе.
- **Направление:** платная/BYOK ключ, другая vision-модель, backoff или очередь запросов.

### BUG-004 — LLM: first-token timeout (6s)

- **Лог:** `[WARNING] neyra.agent: LLM first-token timeout | attempt=1/2 | timeout=6.0s`, затем часто успешный `primary_retry`.
- **Интерпретация:** пики задержки upstream; не падение, но задержка UX.
- **Направление:** поднять `primary_first_token_timeout_seconds` или оставить как есть при приемлемой частоте.

### BUG-005 — Discord Gateway: обрывы WebSocket и reconnect

- **Лог:** множественные `discord.client: Attempting a reconnect`, `ClientConnectorError: Cannot connect to host gateway-*.discord.gg:443`, `ConnectionTimeoutError`, после чего часто `successfully RESUMED`.
- **Интерпретация:** сеть / Discord / локальный DNS; клиент восстанавливает сессию.
- **Направление:** мониторинг как наблюдение; при частых сбоях — сеть, VPN, firewall.

### BUG-006 — Музыка: `music.play => failed` и Lavalink / источники

- **Наблюдения из лога:**
  - Запрос с **Discord custom emoji** в тексте (`<a:Dadada:…>`) → `handled music.play => failed`.
  - Длинные/разговорные запросы с матом и альбомом → `failed` (поиск не нашёл или источник отказал).
  - **Soundcloud URL** → `FriendlyException: Something went wrong while looking up the track`, в WARN повторяется формулировка `youtube search` при этом это общий путь поиска трека.
- **Направление:** санитизация query (убирать `<…>` эмодзи / упоминания), улучшить сообщения об ошибке пользователю, при необходимости отдельный источник Soundcloud в Lavalink / явная ветка для URL.

### BUG-007 — Стабильность рантайма: частые строки `cyber-core: Старт | mode=core`

- **Лог:** за короткий интервал (вечер 2026-05-02) несколько подряд полных стартов ядра (перезапуск процесса).
- **Интерпретация:** смесь ручных перезапусков и возможных падений после ошибок — по одному логу причину не разделить.
- **Направление:** при повторении без ручного рестарта — собрать exit-код, Windows Event, воспроизведение.

### Наблюдения (не регистрируем как баг продукта)

- `**davey is not installed, voice will NOT be supported`** — ожидаемое предупреждение discord.py до установки опционального модуля для голоса.
- **Health monitor OK** — периодические записи штатны.

## 7.6) Legacy и fallback (этап F+) — что ещё поддерживается для старых конфигов

Перед полным отказом от обратной совместимости имеет смысл пройтись по этим точкам и удалить ветки после миграции всех деплоев.


| Механизм                                                                                                                     | Где                                                                             | Назначение                                                                           |
| ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `**openrouter.model*`*, `**openrouter.primary_model*`*                                                                       | `core/llm_profile.py` → `resolved_talk_model`                                   | Старый «главный» id модели → как talk, с **warning** в лог.                          |
| `**openrouter.reflection_model`**                                                                                            | `resolved_memory_model`                                                         | Fallback для memory lane, **warning**.                                               |
| `**async_reflection.model`** в YAML                                                                                          | `resolved_memory_model`, предупреждение в `**core/agent.py`** если ключ задан   | Игнорируется в пользу `**memory_model`.**                                            |
| Плоские ключи на корне `**openrouter`** (`reply_max_tokens`, `brain_max_tokens`, `reflection_*`, `vision_*` без вложенности) | `expand_openrouter_nested` + копирование неролевых ключей                       | Работают параллельно с вложенными блоками.                                           |
| `**resolved_primary_model()`**                                                                                               | `core/llm_profile.py`                                                           | Алиас на `**resolved_talk_model`**.                                                  |
| `**self.llm_primary**`, `**llm_primary_model**`, `**get_stats()["model"]**`                                                  | `core/agent.py`                                                                 | Совместимость со старым кодом/клиентами; по сути = talk.                             |
| `**llm_reflection**`, `**llm_reflection_model**`                                                                             | `core/agent.py`, `core/reflection.py`                                           | Указывают на ту же инстанцию/имя, что и **memory**.                                  |
| Корневой YAML-блок `**vision:`**                                                                                             | `merged_vision_pipeline`                                                        | Подмешивается **ниже приоритета**, чем `**openrouter.vision_model`**, с **warning**. |
| `**DEPRECATED_MODEL_MAP` / `DEPRECATED_OPENROUTER_MODELS`**                                                                  | `core/llm_profile.py`, `core/agent.py`                                          | Подмена устаревших id моделей OpenRouter.                                            |
| `**SCREEN_PROXY_SECRET` → `screen_proxy_plugin`**                                                                            | `core/secrets_loader.py`                                                        | Заглушка под будущий плагин; не `**vision.screen_proxy`**.                           |
| Allowlist `**openrouter.model**`                                                                                             | `interfaces/internal_api/api_server.py`                                         | Обновление старого пути через API.                                                   |
| Документация **корневого `vision`**                                                                                          | `docs/*/setup/config-reference.md` (обновлено на `**openrouter.vision_model**`) | Ранее могла расходиться с кодом.                                                     |


**Что ещё может отставать от «идеальной» схемы (не fallback, а технический долг):**

- Упоминания **«VL-ход»** / старых формулировок только в **логах / BUG-*** в этом файле — не влияют на конфиг.
- Плагин `**interfaces/laptop_screen/`** — заглушка под локальный screen pipeline; не связан с текущим `vision_model` в ядре.

---

## 8) Backlog (дальний горизонт)

- **Интеграция с Obsidian — визуализация «мозга» Нейры.**
  - Экспорт и периодическая синхронизация долгосрочной памяти (LTM), записей рефлексии / дневника и досье PeopleDB в локальный vault как обычные Markdown-файлы.
  - Двунаправленные ссылки в стиле Obsidian (`[[имя_заметки]]`) поверх экспортируемых сущностей, чтобы в **Graph View** были видны связи между фактами, людьми и сформулированными «мыслями» агента.
  - Естественное продолжение философии **этапа D (Local-first)**: зеркало памяти живёт на диске пользователя, без необходимости отдавать смысл облачным БД для просмотра и навигации.
  - Техника: либо лёгкие Python-сервисы/CLI для записи и обновления `.md` в vault с учётом slug и конфликтов, либо подключение готового MCP-сервера для Obsidian в рамках **E2** (Нейра как MCP-клиент), либо комбинация обоих слоёв.
- Desktop и mobile-lite клиенты.
- Standalone `.exe` сборка и/или строгая модель `server-core + lightweight clients`.
- Настройка LLM из Web UI (выбор модели, правка system prompt без ручного `config.yaml`) — после безопасного hot-reload ядра.
- Device-mode (AI station).
- Open-core модель расширений.
- Публичный demo/BYOK режим.