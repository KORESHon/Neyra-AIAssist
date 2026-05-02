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
| `neyra_fire_event` | `POST /v1/debug/fire_event` — публикация в Event Bus |
| `neyra_read_config` | Чтение корневого `config.yaml` с маскированием секретов |
| `neyra_write_config` | `POST /v1/config/update` — только разрешённые поля ядра |
| `neyra_inspect_memory` | `GET /v1/debug/memory` — STM + статистика + RAG |

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