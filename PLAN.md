# PLAN.md — дорожная карта Neyra

**Фокус:** ядро и плагины готовы; **дашборд** в `frontend/` (Vite + React) подключён к Internal API; дальше — **чат в браузере**, затем **демо на GitHub Pages**. ИИ-станция и тяжёлые device-сценарии — в [Future backlog](#future-backlog).

**Следующий согласованный порядок работ:**

1. **Микро-сайт** — дашборд, документация API, вебхуки/оповещения (бывш. 2.3), управление плагинами из UI.
2. **Чат Нейры в браузере** — клиент к существующему Internal API / WebSocket (`/v1`, `/v1/ws/chat`), статика или лёгкий фронт в репозитории (`site/` или `frontend/`).
3. **Одностраничный GitHub Pages** — публичный демо-режим (ограниченный чат/превью + ссылка на репозиторий), без секретов в репо.

Далее по дорожке: безопасность (6) → Voice/Screen/Music (5.2) → локальные клиенты (3.x).

---

## Выполнено (кратко + что прогнать)


| Этап    | Суть                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Проверки                                                                     |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| **1.1** | Единый OpenAI-compatible LLM-слой (`core/llm_profile.py`), backend из `config.yaml`                                                                                                                                                                                                                                                                                                                                                                                                                             | Переключение `BACKEND` / профилей; `scripts/healthcheck.py`                  |
| **1.2** | Event Bus + identity (`core/event_bus.py`, `core/identity.py`)                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Discord/API: события; `user_id` в памяти                                     |
| **1.3** | Двухуровневая рефлексия (`core/reflection.py`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | `/reflect`, ночной cron                                                      |
| **1.4** | Health monitor (`core/health_monitor.py`), JSONL                                                                                                                                                                                                                                                                                                                                                                                                                                                                | `logs/health_status.jsonl`                                                   |
| **1.5** | PeopleDB (`core/memory.py`, инструменты)                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | `/person`, `/v1/memory/`*                                                    |
| **2.1** | Internal REST API в плагине `interfaces/internal_api/` (`api_server.py`): chat, memory, notify, health, stats, config/update, backup                                                                                                                                                                                                                                                                                                                                                                            | `python main.py` (core); curl/OpenAPI; Bearer опционально                |
| **2.2** | WebSocket `/v1/ws/chat`, `/v1/ws/audio` в том же приложении                                                                                                                                                                                                                                                                                                                                                                                                                                                     | `ws://` локально; WSS — `docs/wss-deploy.md`                                 |
| **2.4** | Бэкап + внешнее хранилище                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | `POST /v1/backup/run`                                                        |
| **4.1** | **Микро-сайт (дашборд):** `frontend/` — React + Vite; сборка в `frontend/dist`; FastAPI раздаёт UI с корня `/` (после `/v1`). `GET /v1/plugins` — список плагинов из `PluginLoader`. Конфиг `dashboard:` (`enabled`, `dist_path`, `require_build`). Сборка: `cd frontend && npm install && npm run build`. | `npm run build`; `python main.py`; открыть `http://127.0.0.1:8787/`; dev: `npm run dev` (прокси на тот же порт). |
| **5.1** | **Plugin SDK:** `core/plugin_sdk.py` (`PluginContext`, `run_plugin_entrypoint`), `core/plugin_loader.py` (`cli_modes` опционально, `import_plugin_module`, реестр). Интерфейсы как плагины: `interfaces/discord_text/`, `interfaces/internal_api/`, `interfaces/local_voice/`, `interfaces/laptop_screen/`, шаблон `interfaces/000EXAMPLE/` (см. HELP.md, HELP-RU.md). Контракт: `main_script` экспортирует `run_plugin(ctx)`; продакшен — вместе с ядром (`python main.py`), отладка — `scripts/invoke_plugin.py`. | `PluginLoader(_PROJECT_ROOT).list_plugins()`; `python main.py` |


---

## В работе / дальше (приоритет сверху вниз)

### 4 Микро-сайт + чат в браузере

- **Сделано (4.1):** дашборд (health, память, плагины), ссылки на OpenAPI/Swagger/ReDoc; плагины — read-only список через API.
- **Дальше:** полноценное управление плагинами из UI (после контракта в ядре).
- **Вебхуки и микро-оповещения** (бывш. 2.3): настройка через UI; в ядре retry/backoff, throttling, dead-letter.
- **Фронт для чата** с Нейрой: клиент к `/v1/ws/chat` и REST, папка `frontend/`.

### GitHub Pages — демо одной страницы

- Статический лендинг + встроенный или связанный демо-чат (ограничения по ключам/модели — только публичные демо-настройки).
- Отдельная ветка или `docs/` + workflow Pages — по мере настройки репозитория.
 Безопасное Демо на GitHub Pages (BYOK — Принеси свой ключ)
Мы делаем красивый чат на React и заливаем его на GitHub Pages.

Хитрость: У сайта нет своего бэкенда! Когда друг открывает сайт, там появляется окошко: "Введите ваш API-ключ OpenRouter, чтобы пообщаться с демо-Нейрой". Сайт шлет запросы напрямую в OpenRouter прямо из браузера друга. Твой кошелек в безопасности, сервер не нужен.

### Дополнения к SDK (по мере необходимости)

- `invoke(plugin_id, payload)` для `lifecycle: on_demand` из ядра/тулов.
- Опционально: `setup` / `handle_event` / `shutdown` в манифесте для долгоживущих плагинов.

### 6 Безопасность

Deny-by-default, allowlist/blocklist FS/process/shell, аудит опасных действий.

### 7 Риски (постоянно)

Изоляция провайдеров, очереди записи, bounded timeout, privacy guard.

### 5.2 Voice / Screen / Music (перед локальными клиентами)

STT/TTS, live WS/WSS, screen-agent, music (Lavalink), опционально RVC.

### 3.x Локальные клиенты (в конце дорожной карты)

Desktop, mobile-lite через API.

---

## Future backlog

- Режим «ИИ-станция», device-интеграция.
- Open-core / платные расширения.
- Поддержка проекта: `README.md` / `README-RU.md` (крипто-адреса).