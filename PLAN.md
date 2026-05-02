<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

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
- **Internal API** + **дашборд** (React + Vite + Tailwind, `frontend/`) + WebSocket `/v1/ws/*` работают; до этапа C основной контур UI — HTTP `/v1`.
- **Этап A завершён:** единый плагин `interfaces/discord/` (текст + музыка), один Discord-клиент, музыка через Lavalink 4.x и актуальные source-плагины / клиенты (в т.ч. обход ограничений YouTube, например ANDROID_VR там, где требуется).
- **Этап E1 (базовый MCP debug) выполнен:** репозиторий `tools/mcp_server` (stdio MCP для Cursor: логи, универсальный HTTP к API, `POST /v1/debug/fire_event`, чтение/точечная запись конфига через API, `GET /v1/debug/memory`). Векторы E2 (Neyra как MCP-клиент) и E3 (sandbox/hot-reload) — впереди.
- Память многослойная (STM/LTM/PeopleDB/Diary/Reflection); **lifecycle LTM и control-plane** — в этапе B.
- Скрипты запуска (`run_neyra.*`), healthcheck и загрузка Lavalink усилены.

---

## 4) Stage-gated roadmap

## Этап A — Discord-контур и стабилизация рантайма

**Цель:** устранить архитектурный долг в Discord-интеграции и завершить стабилизацию музыки.

- ~~Слить `discord_text` и `discord_music` в единый плагин `discord`.~~ **Сделано:** resident-плагин `interfaces/discord/` (`bot.py` + `music.py`), старые плагины удалены.
- ~~Использовать один инстанс Discord-клиента для всей гильдии.~~ **Сделано:** клиент поднимается один раз в `interfaces/discord/bot.py`.
- ~~Внутри плагина выделить подмодули (`text` и `music`) как Cogs/сервисы.~~ **Сделано:** разделение `bot.py` (text/gateway) и `music.py` (music service + Lavalink adapter).
- ~~**Критично:** даже внутри единого плагина взаимодействие модулей оставлять через Event Bus (`MUSIC_PLAY` и прочие `MUSIC_`*), а не прямыми вызовами.~~ **Сделано:** Discord-модуль публикует/слушает только `MUSIC_`* события.
- ~~Устранить текущие edge-cases playback/search/queue.~~ **Сделано:** добавлены failover, timeout/pending, безопасные queue embeds и пагинация.
- ~~Зафиксировать backward-compatible формат payload/result для MUSIC-событий.~~ **Сделано:** результат нормализован для event/invoke и публикуется через `MUSIC_RESULT`.

**Критерии приемки:**

- В рантайме отсутствует дублирование Discord-клиентов.
- Модуль `music` стабильно обрабатывает play/queue/skip/pause/resume/stop.
- Нет деградации API/UI, использующих MUSIC-события.

**Статус этапа A: завершён.** Все пункты ручной приёмки ниже успешно пройдены.

### Ручная приёмка Discord (только то, что без живого клиента не проверить)

Остальное (скрипты, `compileall`, healthcheck, размер `Lavalink.jar`, LFS, пути с `!` в Windows) покрывается репозиторием и лаунчерами; здесь — только сценарии из Discord.

**Перед тестом (один раз)**

- Lavalink реально слушает порт из `discord.music.nodes` (после `run_neyra` пункт **3** или автостарта в **2**): в логах нет бесконечного «connection refused» к `127.0.0.1:2333`.
- JAR не pointer: `python scripts/fetch_lavalink.py` (или `git lfs pull` по желанию).

**Slash и текст**

- Slash-команды видны и отвечают (хотя бы `time` / `reset`).
- Обычное сообщение в канале (или с mention по правилам): ответ агента приходит, стрим/финал соответствует ожиданию.

**Музыка (в голосе)**

- Без войса: play/очередь → понятная ошибка в чате.
- В войсе: play (текст + при желании URL), очередь с кнопками ◀/▶, skip / pause / resume / stop / clear — поведение совпадает с ожиданием.
- Долгий ответ: сообщение «долго думаю» не ломает повторную команду.

**Запись для перехода на E1**

- **Среда:** Windows, Java 25, локальный Lavalink (v4.2.2) с обновлёнными клиентами (ANDROID_VR для обхода sig function).
- **Текст:** Slash-команды работают (`/time`, `/reset`). Агент корректно отвечает на текстовые сообщения с учётом памяти. Зависаний при долгих запросах LLM нет.
- **Музыка (защита):** защита от дурака работает (требует зайти в войс).
- **Музыка (плеер):** поиск (`ytsearch`), добавление в очередь, воспроизведение (OPUS codec) работают стабильно. Управление (skip, pause, resume, stop) отрабатывает без сбоев. Обход блокировок YouTube успешен.
- **Статус:** этап A официально завершён.

**Этап E1 (MCP debug)** по базовому контуру закрыт: см. `tools/mcp_server` и раздел **Этап E** ниже.

**Следующий приоритет roadmap:** **этап C** — двусторонний WebSocket-мост **Web UI ↔ Event Bus**. Параллельно в плане — **этап B** (мультиюзер и lifecycle памяти).

## Этап B — Контекст, память и безопасность control-plane

**Цель:** исправить путаницу пользователей в групповых чатах и сделать память управляемой.

### B1. Многопользовательский контекст (Speaker ID Injection)

- В STM и/или формат сообщений LLM вводится явное авторство user-реплик:
  - пример: `[Пользователь Maxim]: ...`
  - либо `name` поле в сообщения, где поддерживается провайдером.
- Discord-плагин обязан прокидывать `author_name` в ядро на каждый ход.

### B2. Динамическое взвешивание памяти (Context Weighting)

- В prompt-сборке PeopleDB разделяется на приоритетные блоки:
  - `Активный собеседник` (highest priority, в начале системного контекста),
  - `Упомянутые люди` (secondary priority, ниже).
- Одинаковая логика для `chat` и `chat_stream`.

### B3. Жизненный цикл LongTermMemory (ChromaDB)

Трехшаговая стратегия:

1. **TTL + Prune-job**
  - TTL для низкоприоритетных/фоновых диалогов,
  - фоновая регулярная очистка.
2. **Summarization -> Cold Archive**
  - старые записи сжимаются в summary-документы,
  - оригиналы уводятся в архив (cold storage).
3. **Операционное API**
  - endpoint-ы обслуживания памяти из dashboard:
    - `/v1/memory/prune`
    - `/v1/memory/summarize`
    - (опционально) `/v1/memory/policies`, `/v1/memory/reindex`

### B4. Security hardening

- Ролевая модель и аудит критичных API-операций.
- Усиление webhook подписи/верификации.
- Rate limiting и anti-abuse.

**Критерии приемки:**

- Нейра корректно различает собеседников в групповых чатах.
- Контекст активного собеседника стабильно доминирует в prompt.
- Размер LTM контролируем, есть штатные операции обслуживания.
- Критичные API защищены.

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
- инъекция событий в шину через `POST /v1/debug/fire_event` (`neyra_fire_event`);
- безопасное чтение корневого `config.yaml` с редакцией секретов (`neyra_read_config`);
- точечные обновления через `POST /v1/config/update` (`neyra_write_config`);
- снимок STM/stats/RAG через `GET /v1/debug/memory` (`neyra_inspect_memory`).

**Остаётся по желанию:** остановка/запуск ядра из IDE, расширенные диагностики — без блокировки этапов B/C.

### E2. Вектор Runtime: Нейра как MCP-клиент

- Внедрить в ядро универсальный MCP-адаптер клиента.
- Дать Нейре возможность подключать стандартизированные MCP-серверы:
  - ОС/терминал,
  - браузер,
  - Home Assistant,
  - почта/календарь,
  - и другие внешние интеграции.
- Цель: минимизировать кастомные Python-интеграции внутри `core`.

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
- Подключение внешних MCP-серверов выполняется без изменения `core`-логики интеграций.
- Самопрограммирование ограничено sandbox-границами.
- Hot-reload/rollback воспроизводимы в тестах.

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

## 8) Backlog (дальний горизонт)

- Desktop и mobile-lite клиенты.
- Standalone `.exe` сборка и/или строгая модель `server-core + lightweight clients`.
- Настройка LLM из Web UI (выбор модели, правка system prompt без ручного `config.yaml`) — после безопасного hot-reload ядра.
- Device-mode (AI station).
- Open-core модель расширений.
- Публичный demo/BYOK режим.