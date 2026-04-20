# PLAN.md — дорожная карта Neyra

## Статус готовности (краткая сводка)


| Область                   | Состояние      | Комментарий                                                                                                                             |
| ------------------------- | -------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Ядро**                  | Готово         | LLM-слой, агент, память (RAG/Chroma), рефлексия, инструменты, PeopleDB, event bus, секреты из `.env`                                    |
| **HTTP API + WS**         | Готово         | FastAPI в `interfaces/internal_api/`: REST `/v1`, WebSocket чат/аудио; bind и дашборд — `interfaces/internal_api/config.yaml`           |
| **Дашборд (frontend)**    | Готово         | Микро-сайт с разделами Home/Dashboard/Plugins/Settings/Webhooks/API Docs; управление плагинами и webhook routes из UI                   |
| **Плагины**               | Разный уровень | `discord_text` — рабочий; `internal_api` — часть ядра HTTP; `local_voice` / `laptop_screen` — **заглушки**; `000EXAMPLE` — шаблон       |
| **Конфигурация**          | Готово         | Корневой `config.yaml` + подмешивание `interfaces/<id>/config.yaml` (`core/plugin_config.py`); вкл/выкл плагина — только `plugin.yaml`  |
| **Операции**              | Готово         | `scripts/healthcheck.py`, backup, внешнее хранилище (адаптеры)                                                                          |
| **Не сделано (см. ниже)** | План           | Полноценный чат-страница в браузере, GitHub Pages demo, hardening безопасности инструментов, Voice/Screen/Music, десктоп/мобайл-клиенты |


**Итог:** проект **живой и пригоден для ежедневного использования** как ядро + Discord + локальная панель. Крупные пробелы — **продуктовый чат-UI**, **управление плагинами** и **публичное демо**.

---

**Фокус развития:** дашборд уже есть; дальше — **чат в браузере**, **управление плагинами**, затем **демо на GitHub Pages**. ИИ-станция и тяжёлые device-сценарии — в [Future backlog](#future-backlog).

**Следующий согласованный порядок работ:**

1. **Микро-сайт** — документация API в UI (частично есть ссылки), вебхуки/оповещения (2.3), **управление плагинами** из панели.
2. **Чат Нейры в браузере** — клиент к `/v1/ws/chat` и REST в `frontend/` (или отдельный лёгкий фронт).
3. **Одностраничный GitHub Pages** — публичный демо-режим (BYOK / ограничения), без секретов в репо.

Далее по дорожке: безопасность (6) → Voice/Screen/Music (5.2) → локальные клиенты (3.x).

---

## Выполнено (кратко + что прогнать)


| Этап     | Суть                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Проверки                                                                                                         |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| **1.1**  | Единый OpenAI-compatible LLM-слой (`core/llm_profile.py`), backend из `config.yaml`                                                                                                                                                                                                                                                                                                                                                                                                                                 | Переключение `BACKEND` / профилей; `scripts/healthcheck.py`                                                      |
| **1.2**  | Event Bus + identity (`core/event_bus.py`, `core/identity.py`)                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Discord/API: события; `user_id` в памяти                                                                         |
| **1.3**  | Двухуровневая рефлексия (`core/reflection.py`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | `/reflect`, ночной cron                                                                                          |
| **1.4**  | Health monitor (`core/health_monitor.py`), JSONL                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | `logs/health_status.jsonl`                                                                                       |
| **1.5**  | PeopleDB (`core/memory.py`, инструменты)                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | `/person`, `/v1/memory/`*                                                                                        |
| **2.1**  | Internal REST API в плагине `interfaces/internal_api/` (`api_server.py`): chat, memory, notify, health, stats, config/update, backup                                                                                                                                                                                                                                                                                                                                                                                | `python main.py` (core); curl/OpenAPI; Bearer опционально                                                        |
| **2.2**  | WebSocket `/v1/ws/chat`, `/v1/ws/audio` в том же приложении                                                                                                                                                                                                                                                                                                                                                                                                                                                         | `ws://` локально; WSS — `docs/wss-deploy.md`                                                                     |
| **2.4**  | Бэкап + внешнее хранилище                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | `POST /v1/backup/run`                                                                                            |
| **4.1**  | **Микро-сайт (дашборд):** `frontend/` — React + Vite; сборка в `frontend/dist`; FastAPI раздаёт UI с корня `/` (после `/v1`). `GET /v1/plugins` — список плагинов из `PluginLoader`. Параметры `dashboard` и bind HTTP/API — в `interfaces/internal_api/config.yaml` (шаблон `config.example.yaml` там), при отсутствии файла — разумные дефолты в коде. Сборка: `cd frontend && npm install && npm run build`.                                                                                                     | `npm run build`; `python main.py`; открыть `http://127.0.0.1:8787/`; dev: `npm run dev` (прокси на тот же порт). |
| **5.1**  | **Plugin SDK:** `core/plugin_sdk.py` (`PluginContext`, `run_plugin_entrypoint`), `core/plugin_loader.py` (`cli_modes` опционально, `import_plugin_module`, реестр). Интерфейсы как плагины: `interfaces/discord_text/`, `interfaces/internal_api/`, `interfaces/local_voice/`, `interfaces/laptop_screen/`, шаблон `interfaces/000EXAMPLE/` (см. HELP.md, HELP-RU.md). Контракт: `main_script` экспортирует `run_plugin(ctx)`; продакшен — вместе с ядром (`python main.py`), отладка — `scripts/invoke_plugin.py`. | `PluginLoader(_PROJECT_ROOT).list_plugins()`; `python main.py`                                                   |
| **5.1b** | **Конфиги плагинов:** `core/plugin_config.py` подмешивает `interfaces/<id>/config.yaml` в общий dict до секретов (`merge` → `apply_env_secrets`). Секции: `discord_text` → `discord`, `internal_api` → `internal_api` + `dashboard`, остальные → `plugins.<id>`. Вкл/выкл и lifecycle **только** в `plugin.yaml`, не в `config.yaml` плагина. Токены — из корневого `.env` (`DISCORD_TOKEN`, `INTERNAL_API_TOKEN`). Корневой шаблон облегчён; локальные `interfaces/**/config.yaml` в `.gitignore`.                 | Шаблоны: `interfaces/*/config.example.yaml`; smoke: `python main.py`, `scripts/healthcheck.py --mode core`       |


---

## В работе / дальше (приоритет сверху вниз)

### 4 Микро-сайт + чат в браузере

- **Сделано (4.1):** дашборд (health, память, баланс LLM, плагины read-only), ссылки на OpenAPI/Swagger/ReDoc.
- **Не сделано:** полноценный **чат с Нейрой в браузере** (клиент к уже существующим `/v1/ws/chat` и REST).
- **Сделано (4.2):** управление плагинами из UI/API (`enable/disable`, config read/write, reload/restart/invoke, operations status).
- **Сделано (4.3):** вебхуки и оповещения: inbound endpoints, outbound routes, deliveries, DLQ, ручной retry и тестирование из UI.

### GitHub Pages — демо одной страницы

- Статический лендинг + демо-чат (ограничения по ключам/модели).
- Отдельная ветка или `docs/` + workflow Pages — по мере настройки репозитория.
- **BYOK:** статический чат; ключ OpenRouter в браузере; запросы с клиента без своего бэкенда.

### Дополнения к SDK (по мере необходимости)

- `invoke(plugin_id, payload)` для `lifecycle: on_demand` из ядра/тулов.
- Опционально: `setup` / `handle_event` / `shutdown` в манифесте для долгоживущих плагинов.

### 6 Безопасность

Deny-by-default, allowlist/blocklist FS/process/shell, аудит опасных действий.

### 7 Риски (постоянно)

Изоляция провайдеров, очереди записи, bounded timeout, privacy guard.

### 5.2 Voice / Screen / Music (перед локальными клиентами)

STT/TTS, live WS/WSS, screen-agent, music (Lavalink), опционально RVC. Сейчас — только заглушки плагинов + облачные адаптеры в конфиге.

### 3.x Локальные клиенты (в конце дорожной карты)

Desktop, mobile-lite через API.

---

## Future backlog

- Режим «ИИ-станция», device-интеграция.
- Open-core / платные расширения.
- Поддержка проекта: `README.md` / `README-RU.md` (крипто-адреса).

