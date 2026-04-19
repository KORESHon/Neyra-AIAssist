# PLAN.md — дорожная карта Neyra

**Фокус:** сначала стабильное ядро, затем интерфейсы и внешние модули. ИИ-станция и тяжёлые device-сценарии — в [Future backlog](#future-backlog).

---

## Выполнено (кратко + что прогнать)

| Этап | Суть | Проверки |
|------|------|----------|
| **1.1** | Единый OpenAI-compatible LLM-слой (`core/llm_profile.py`), backend из `config.yaml` | Переключение `BACKEND` / профилей; `scripts/healthcheck.py` (и `--skip-http` при необходимости) |
| **1.2** | Event Bus + identity (`core/event_bus.py`, `core/identity.py`), события chat/memory/notify | Discord: ответ + события; запись `user_id` в долгую память |
| **1.3** | Двухуровневая рефлексия (`core/reflection.py`), дедуп/фильтр, запись в PeopleDB/дневник | Ручной `/reflect`, ночной cron; нет мусора в LTM |
| **1.4** | Health monitor (`core/health_monitor.py`), JSONL `logs/health_status.jsonl` | Запуск ядра с включённым `health_monitor`; строки в JSONL |
| **1.5** | PeopleDB вместо FriendsDB (`core/memory.py`, инструменты `get_person_info` / `update_person_fact`) | `/person`, API `/v1/memory/*`, без старых имён в коде/путях |
| **2.1** | Internal REST API (`interfaces/internal_api.py`): chat, memory, notify, health, stats, config/update, backup/run | `python main.py --mode api`; curl/OpenAPI к `/v1/*`; опционально Bearer |
| **2.2** | Тот же FastAPI как gateway: WebSocket `/v1/ws/chat`, `/v1/ws/audio`; таймауты/ping в конфиге | Локально `ws://`; прод — WSS за reverse-proxy (`docs/wss-deploy.md`) |
| **2.4** | Бэкап + внешнее хранилище (`core/backup_manager.py`, `core/external_storage.py`), синк после большой рефлексии | `POST /v1/backup/run`; `local_folder` / при `pydrive2` — `google_drive` |
| **5.1 (prep)** | Загрузчик плагинов + пример `interfaces/example/` (`plugin.yaml`, `main_script`, `enabled`) | Скан каталога; `enabled: false` не грузит runtime |

---

## В работе / дальше

### 2.3 Webhook / Notifier
Discord webhook, Telegram, generic HTTP; retry/backoff, throttling, dead-letter.

### 3.x Локальные клиенты
Desktop (UI + ОС-команды в allowlist), mobile-lite через API.

### 4 Микро-сайт
Дашборд, мини-панель, OpenAPI/Swagger, флаг совместного запуска с ядром.

### 5.1 Plugin SDK (полный)
Контракт `setup` / `handle_event` / `shutdown`, изоляция, документация для авторов модулей.

### 5.2 Voice / Screen / Music
STT/TTS factories, **live WS/WSS** (абстракции, fallback REST, reconnect), screen-agent, music (Lavalink), опционально RVC — см. детальный чеклист в истории репозитория при необходимости.

### 6 Безопасность
Deny-by-default, allowlist/blocklist FS/process/shell, аудит опасных действий.

### 7 Риски (постоянно)
Изоляция провайдеров, очереди записи, bounded timeout, privacy guard.

---

## Future backlog

- Режим «ИИ-станция» (умная колонка / домашний хаб).
- Глубокая device-интеграция (GPIO / IoT / voice-first).
- Второстепенно: донаты в README, open-core плагины, лендинг на GitHub Pages.
