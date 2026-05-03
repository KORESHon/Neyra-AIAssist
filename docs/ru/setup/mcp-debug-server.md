<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# MCP debug-сервер (`tools/mcp_server`)

Официальный Python SDK MCP (`mcp`): подключение Cursor к Нейре для логов, вызовов Internal API, инъекции событий и инспекции памяти.

**Инструменты**

| Tool | Назначение |
|------|------------|
| `read_neyra_logs` | Хвост `logs/system.log` (или путь из конфига / `NEYRA_LOG_PATH`) |
| `neyra_api_request` | Произвольный HTTP к Internal API (`GET`/`POST`/…) |
| `neyra_health` | `GET /v1/health` — быстрый ping ядра |
| `neyra_lifecycle` | `POST /v1/debug/lifecycle` — **stop**/**restart** процесса (нужен admin-токен и включённый lifecycle; см. ниже) |
| `neyra_fire_event` | `POST /v1/debug/fire_event` — публикация в Event Bus |
| `neyra_read_config` | Чтение корневого `config.yaml` с маскированием секретов |
| `neyra_write_config` | `POST /v1/config/update` — только разрешённые поля ядра |
| `neyra_inspect_memory` | `GET /v1/debug/memory` — STM + статистика + RAG |

**Lifecycle (`neyra_lifecycle`):** по умолчанию выключен (API вернёт **403**), пока не задано `internal_api.debug_lifecycle_enabled: true` или переменная `NEYRA_DEBUG_LIFECYCLE=1`/`true`/`yes` (в `docker-compose.yml` для сервиса задаётся автоматически). Нужен **admin** Bearer (`INTERNAL_API_TOKEN`). Действия **stop** и **restart** завершают процесс Python; повторный запуск в Docker даёт политика `restart: unless-stopped` или ручной `docker compose restart`.

**Docker Desktop:** из корня репозитория `docker compose up --build`; на хосте MCP указывает `NEYRA_API_BASE=http://127.0.0.1:8787`. Логи в томе `./logs` на хосте совпадают с путём репозитория — `read_neyra_logs` работает из того же чекаута или через `NEYRA_LOG_PATH`. Секреты — в `.env` (см. `.env.example`). Не публикуйте вывод `docker compose config`, если в нём подставляются секреты из `.env`.

## Установка

Из корня репозитория:

```bash
python -m venv .venv-mcp
.venv-mcp\Scripts\activate
pip install -r tools/mcp_server/requirements.txt
```

## Путь к логу

1. Переменная `NEYRA_LOG_PATH`.
2. Иначе `logging.system_log` в корневом `config.yaml` (как у `main.py`, обычно `./logs/system.log`).
3. Иначе первый существующий файл: `logs/system.log`, затем `logs/neyra.log`.
4. Иначе ожидаемый путь по умолчанию: `logs/system.log`.

## Подключение в Cursor

**Cursor Settings → MCP**, сервер **stdio**:

- **Command:** интерпретатор Python с установленными зависимостями.
- **Args:** полный путь к `tools/mcp_server/server.py`.

Пример `env`: `NEYRA_LOG_PATH`, `NEYRA_API_BASE` (`http://127.0.0.1:8787`), `NEYRA_API_TOKEN` (если задан `internal_api.token`), `NEYRA_CONFIG_PATH`.

Подробный пример JSON см. в английской версии: [mcp-debug-server.md](../../en/setup/mcp-debug-server.md) (блоки с `mcpServers`).

## Реализация

Файлы: `tools/mcp_server/server.py`, `tools/mcp_server/requirements.txt`.