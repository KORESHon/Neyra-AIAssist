# Neyra Plugin SDK — Tutorial & Reference (English)

**Other language:** [HELP-RU.md](HELP-RU.md) (Русский)

This guide is both a **tutorial** and a **reference**: what plugins are for, what you should and should not do, a Hello World walkthrough, and pointers to real code in the repo.

---

## Table of contents

1. [Philosophy](#philosophy)
2. [What you can build (capabilities)](#what-you-can-build-capabilities)
3. [What you must not do (anti-patterns)](#what-you-must-not-do-anti-patterns)
4. [Tutorial: Hello World plugin](#tutorial-hello-world-plugin)
5. [Reference: layout & manifest](#reference-layout--manifest)
6. [Reference: `PluginContext` & `run_plugin`](#reference-plugincontext--run_plugin)
7. [How `main.py` wires CLI modes](#how-mainpy-wires-cli-modes)
8. [Loader API](#loader-api)
9. [Reference implementations](#reference-implementations)
10. [Checklist before sharing your plugin](#checklist-before-sharing-your-plugin)
11. [Troubleshooting](#troubleshooting)

---

## Philosophy

A **plugin** is an isolated folder under `interfaces/<name>/`. The core discovers `interfaces/*/plugin.yaml` and loads your entry module only when needed (depending on `lifecycle`, CLI mode, or future `invoke` APIs). **Removing a plugin folder must not break the core** — that is the main design rule.

---

## What you can build (capabilities)

With access to `PluginContext`, a plugin can:

- **Add interfaces (entry points):** e.g. another chat transport (Telegram, VK, local STT pipeline), similar to `discord_text`.
- **Run background workers:** periodic jobs (RSS, email checks) that write facts through the same memory APIs the core uses — follow async and process boundaries carefully.
- **Embed servers:** run FastAPI/uvicorn inside the process, like `internal_api` (`api_server.py`).
- **Use the core:** read `ctx.config`, and either use `ctx.agent` when the launcher passes it (e.g. Discord) or construct `NeyraAgent(ctx.config)` inside the plugin (like the API does). Prefer **not** calling raw OpenAI SDKs from the plugin — route LLM calls through `NeyraAgent` so models, logging, and safety stay consistent.

---

## What you must not do (anti-patterns)

| Do not | Why |
|--------|-----|
| **Patch files under `core/` from a plugin** | Plugins must stay removable. Put logic in `interfaces/<your_plugin>/`. |
| **Commit secrets in `plugin.yaml` or source** | Tokens belong in `.env` and are merged into `ctx.config` via `core/secrets_loader.py`. |
| **Block the whole event loop without reason** | For long-running work inside a shared process, prefer `asyncio` and non-blocking I/O. Dedicated CLI modes (Discord, uvicorn) may block their thread by design. |
| **Bypass `NeyraAgent` for LLM calls** | Do not embed ad-hoc `openai` clients for assistant replies — use `NeyraAgent` so configuration and tracing stay centralized. |
| **Reuse production `cli_modes` names** | Do not register `discord`, `api`, etc., for experiments — pick unique names. |

---

## Tutorial: Hello World plugin

### Step 1 — Create a folder

```text
interfaces/my_hello_plugin/
```

Use a unique folder name (lowercase and underscores are fine).

### Step 2 — Add `plugin.yaml`

```yaml
id: hello_world
name: Hello World Plugin
description: Minimal SDK demo
version: "1.0.0"
enabled: true
lifecycle: on_demand
cli_modes:
  - hello
main_script: main.py
```

### Step 3 — Add `main.py` at the plugin root

`NeyraAgent.chat` is **async**. For a blocking `run_plugin`, use `asyncio.run`. The stock `main.py` only passes `ctx.agent` for **Discord**; for other modes, create an agent inside the plugin (same idea as `internal_api`).

```python
from __future__ import annotations

import asyncio

from core.agent import NeyraAgent
from core.plugin_sdk import PluginContext


def run_plugin(ctx: PluginContext) -> None:
    print(f"[hello_world] project root = {ctx.root}")

    async def _run() -> None:
        agent = ctx.agent or NeyraAgent(ctx.config)
        out = await agent.chat(
            "Reply with one short English sentence: Hello from the plugin tutorial.",
            username="hello_world",
        )
        print("[hello_world] model reply:", (out or {}).get("text", out))

    asyncio.run(_run())
```

### Step 4 — Run

```bash
python main.py --mode hello
```

If two plugins register the same `cli_modes` entry, the loader keeps one (a warning is logged). Use a **unique** mode name.

### Disabling the template `000EXAMPLE`

The shipped template under `interfaces/000EXAMPLE/` stays **`enabled: false`** and has **no** `cli_modes` so it never conflicts with your modes. Copy it as a starting point, or follow the layout above from scratch.

---

## Reference: layout & manifest

Typical layout:

```text
interfaces/000EXAMPLE/
  plugin.yaml
  HELP.md
  HELP-RU.md
  help.html
  core/
    main.py       # if main_script points here
```

Shipped plugins: `discord_text/`, `internal_api/`, `local_voice/`, `laptop_screen/`.

### `plugin.yaml` fields

| Field | Meaning |
|-------|---------|
| `id` | Unique string id. |
| `name`, `description`, `version` | Metadata for registry / UI. |
| `enabled` | If `false`, `python main.py --mode …` for this plugin’s mode will exit with an error. |
| `lifecycle` | `resident` — eligible for eager load paths; `on_demand` — skip eager import where the loader supports it. |
| `cli_modes` | Strings that match `python main.py --mode <name>`. Empty if you only use programmatic loading later. |
| `main_script` | Path to the entry `.py` file, relative to the plugin directory. |

Reserved keys such as `events`, `commands`, `permissions` are for future dashboard / SDK features.

---

## Reference: `PluginContext` & `run_plugin`

The entry module **must** export:

```python
def run_plugin(ctx: PluginContext) -> None:
    ...
```

`PluginContext` (`core/plugin_sdk.py`):

- `root: Path` — repository root.
- `config: dict` — full YAML config after `.env` overlays.
- `agent` — `NeyraAgent` or `None`. Today, `main.py` injects an agent for **Discord** only; other modes should call `NeyraAgent(ctx.config)` if they need the agent.

---

## How `main.py` wires CLI modes

- `core/plugin_loader.PluginLoader.manifest_for_cli_mode(mode)` finds the plugin whose `cli_modes` contains `mode`.
- If the manifest is missing or `enabled: false`, startup fails.
- The entry module is loaded with `import_plugin_module`, then `run_plugin_entrypoint` calls `run_plugin(ctx)`.

---

## Loader API

- `core/plugin_loader.py` — `PluginLoader`, `discover_manifests()`, `list_plugins()`, `cli_mode_index()`, `import_plugin_module()`, `manifest_for_cli_mode()`, `set_enabled()`.
- `core/plugin_sdk.py` — `PluginContext`, `run_plugin_entrypoint`.

---

## Reference implementations

| Plugin | Role |
|--------|------|
| `interfaces/discord_text/` | Discord client, uses injected `ctx.agent`. |
| `interfaces/internal_api/` | FastAPI + uvicorn; builds its own `NeyraAgent` in `build_app`. |
| `interfaces/local_voice/`, `interfaces/laptop_screen/` | Stubs for future work. |

---

## Checklist before sharing your plugin

- [ ] No secrets in the repo — only `.env` / config keys documented in `.env.example`.
- [ ] Unique `id` and unique `cli_modes` values vs other plugins.
- [ ] `enabled` default appropriate for public clones (`false` if it needs local credentials).
- [ ] LLM traffic goes through `NeyraAgent` (unless you have a rare, documented exception).
- [ ] README or HELP snippet for users who install your folder under `interfaces/`.

---

## Troubleshooting

**`No plugin registers cli_mode`** — Check `cli_modes` spelling and `enabled: true`.

**Import errors** — Run from project root so `core.*` imports resolve; use the same layout as shipped plugins.

**Agent is `None`** — Expected for non-Discord modes; instantiate `NeyraAgent(ctx.config)` in the plugin.

**Duplicate mode warning** — Two manifests list the same `cli_modes` entry; rename your mode.
