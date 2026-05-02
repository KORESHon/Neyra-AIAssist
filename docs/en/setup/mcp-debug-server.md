<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# MCP debug server (`tools/mcp_server`)

Official Python MCP SDK (`mcp` package): connect Cursor (or any MCP client) to Neyra for logs, Internal API calls, event injection, and memory inspection.

## Tools

| Tool | Purpose |
|------|---------|
| `read_neyra_logs` | Tail `logs/system.log` (or path from config / `NEYRA_LOG_PATH`) |
| `neyra_api_request` | Arbitrary HTTP to Internal API (`GET`/`POST`/…) |
| `neyra_fire_event` | `POST /v1/debug/fire_event` — publish to Event Bus |
| `neyra_read_config` | Read root `config.yaml` with secret redaction |
| `neyra_write_config` | `POST /v1/config/update` — only allow-listed keys |
| `neyra_inspect_memory` | `GET /v1/debug/memory` — STM + stats + RAG |

## Install

From the repository root:

```bash
python -m venv .venv-mcp
# Windows: .venv-mcp\Scripts\activate
pip install -r tools/mcp_server/requirements.txt
```

## Log file resolution

1. `NEYRA_LOG_PATH` if set.
2. Otherwise `logging.system_log` in root `config.yaml` (same as `main.py`, usually `./logs/system.log`).
3. Otherwise first existing file: `logs/system.log`, then `logs/neyra.log`.
4. Default expected path: `logs/system.log`.

## Cursor MCP (stdio)

In **Cursor Settings → MCP**, add a stdio server:

- **Command:** Python interpreter with deps installed (e.g. `.venv-mcp\Scripts\python.exe`).
- **Args:** full path to `tools/mcp_server/server.py`.

Example JSON (adjust paths):

```json
{
  "mcpServers": {
    "neyra-debug": {
      "command": "Z:\\path\\to\\AIAssist\\.venv-mcp\\Scripts\\python.exe",
      "args": ["Z:\\path\\to\\AIAssist\\tools\\mcp_server\\server.py"]
    }
  }
}
```

Optional `env` for the server:

- `NEYRA_LOG_PATH` — explicit system log path.
- `NEYRA_API_BASE` — API base URL (default `http://127.0.0.1:8787`).
- `NEYRA_API_TOKEN` — Bearer token if `internal_api.token` is set in `config.yaml` (required for HTTP tools).
- `NEYRA_CONFIG_PATH` — alternate path to `config.yaml` for `neyra_read_config`.

With token:

```json
{
  "mcpServers": {
    "neyra-debug": {
      "command": "Z:\\path\\to\\AIAssist\\.venv-mcp\\Scripts\\python.exe",
      "args": ["Z:\\path\\to\\AIAssist\\tools\\mcp_server\\server.py"],
      "env": {
        "NEYRA_API_TOKEN": "your_token_from_config"
      }
    }
  }
}
```

Restart MCP / Cursor. Verify `read_neyra_logs`, then `neyra_api_request` with `GET` `/v1/health`.

## Implementation

Runtime files: `tools/mcp_server/server.py`, `tools/mcp_server/requirements.txt`.