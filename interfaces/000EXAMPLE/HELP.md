# Neyra Plugin SDK — Tutorial & Reference (English)

**Russian (same full scope, separate file):** [HELP-RU.md](HELP-RU.md)

This document is the **full English tutorial** for plugin authors: what plugins are, what you can realistically build (including international integrations), what is **not realistically achievable** inside a plugin alone (limits, not “rules”), how to load **your own config files** and **your own `.env` keys**, anti-patterns, Hello World, and API reference.

---

## Table of contents

1. [Philosophy](#philosophy)
2. [What you can realistically build](#what-you-can-realistically-build)
3. [Architectural limits (what a plugin alone cannot do)](#architectural-limits-what-a-plugin-alone-cannot-do)
4. [Rules of thumb (anti-patterns)](#rules-of-thumb-anti-patterns)
5. [Your own config file inside the plugin](#your-own-config-file-inside-the-plugin)
6. [Your own secrets from `.env](#your-own-secrets-from-env)`
7. [Tutorial: Hello World plugin](#tutorial-hello-world-plugin)
8. [Reference: layout & manifest](#reference-layout--manifest)
9. [Reference: `PluginContext` & `run_plugin](#reference-plugincontext--run_plugin)`
10. [How `main.py` wires CLI modes](#how-mainpy-wires-cli-modes)
11. [Loader API](#loader-api)
12. [Reference implementations](#reference-implementations)
13. [Checklist before sharing your plugin](#checklist-before-sharing-your-plugin)
14. [Troubleshooting](#troubleshooting)

---

## Philosophy

A **plugin** is an isolated folder under `interfaces/<name>/`. The core discovers `interfaces/*/plugin.yaml` and loads your entry module when needed. **Deleting the plugin folder must not break the core** — that is the main design rule.

---

## What you can realistically build

Plugins run **in the same Python process** as Neyra (unless you spawn a subprocess yourself). You can:

- **New chat / event transports:** bridges to other networks — e.g. Telegram, Slack, Microsoft Teams, **Meta (Facebook) Messenger / Instagram** via their official APIs where available, **X (Twitter)**, **Reddit**, forums — anything with HTTP webhooks or REST.
- **Search & knowledge:** wrap **Google Custom Search**, **Bing Web Search**, **Yandex Search**, **Brave Search**, SerpAPI, etc., and feed snippets into the agent or memory (respect each provider’s Terms of Service).
- **Media:** **YouTube Data API** (metadata, captions where allowed), Google Drive / Dropbox for user-authorized file access (OAuth in the plugin).
- **Voice / STT / TTS:** call cloud or local APIs from your plugin; keep keys in `.env` and tuning in a **plugin-local config** (see below).
- **Embedded HTTP servers:** FastAPI/uvicorn like `internal_api`, or a minimal webhook receiver.
- **Background logic:** periodic tasks (with care not to block the whole process) — RSS, calendars, custom “if this then notify”.
- **Core integration:** read `ctx.config` (global Neyra config); use `ctx.agent` when provided, or `NeyraAgent(ctx.config)` for assistant replies so routing and logging stay consistent.

Anything that is “call an HTTP API + optional OAuth” is usually fair game **if** you implement auth and rate limits yourself.

---

## Architectural limits (what a plugin alone cannot do)

These are **limitations of reality and architecture**, not “forbidden by policy”:

- **You cannot change the shipped core’s code** from a plugin — plugins do not patch `core/` at runtime. To change kernel behavior you edit the repo or fork. A plugin only adds code under `interfaces/<id>/`.
- **You cannot grant OS permissions** (microphone, screen recording, admin) — the OS still asks the user; the plugin only uses what the process already has.
- **You cannot bypass third-party platform rules** — Meta, Google, YouTube, etc. each have API and ToS constraints; compliance is the integrator’s responsibility.
- **You cannot assume a GPU** — the plugin runs in Neyra’s process; heavy ML may need a separate service or subprocess you manage.
- **You cannot magically merge two unrelated identities** — linking accounts across platforms still needs your own mapping logic and user consent.
- **Long blocking work** in the same process can stall other interfaces — very heavy jobs should be **async**, **offloaded to a thread/process**, or a separate microservice.

---

## Rules of thumb (anti-patterns)


| Avoid                                                               | Why                                                                                                         |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Editing files under `core/` from plugin code                        | Keeps plugins removable.                                                                                    |
| Committing secrets in `plugin.yaml` or in tracked source            | Use `.env` and document variable names in `.env.example`.                                                   |
| Blocking the asyncio thread without reason                          | Prefer async I/O or a dedicated subprocess for heavy work.                                                  |
| Bypassing `NeyraAgent` for **assistant** replies                    | Use `NeyraAgent` so models and logs stay centralized (raw HTTP to **other** APIs for search/music is fine). |
| Stealing reserved `cli_modes` names (`discord`, `api`, …) for tests | Pick a unique mode name.                                                                                    |


---

## Your own config file inside the plugin

Use a **second file** next to your code — e.g. `config.yaml`, `settings.yaml`, or `voice.yaml` — for options that belong to the plugin only (voice profile, API base URL for a custom search, feature flags).

**Pattern:** resolve paths relative to the plugin directory (not the cwd), so it works from any launch directory.

```python
from __future__ import annotations

from pathlib import Path

import yaml

from core.plugin_sdk import PluginContext


def _plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def load_plugin_settings() -> dict:
    cfg_path = _plugin_dir() / "config.yaml"
    if not cfg_path.is_file():
        return {}
    with cfg_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def run_plugin(ctx: PluginContext) -> None:
    local = load_plugin_settings()
    global_voice = (ctx.config.get("voice_cloud") or {}).get("stt") or {}
    # Example: plugin override for a custom STT endpoint
    endpoint = local.get("custom_stt_url") or global_voice.get("base_url")
    ...
```

- You may **merge** plugin config with `ctx.config` in code (your naming — e.g. `local.get("timeout", 30)`).
- **Do not** put secrets in this file; put placeholders and read secrets from `.env` (next section).
- Optionally add `interfaces/<your_plugin>/config.example.yaml` in the repo (no secrets) so users can copy to `config.yaml`.

---

## Your own secrets from `.env`

The project already calls `load_dotenv` from `**main.py`** before config load, so **at `run_plugin` time** `os.environ` contains variables from the root `.env`.

**Example — custom Yandex Search (or any) API key:**

1. User adds to `**.env`** (root of repo, next to `main.py`):
  ```env
   YANDEX_SEARCH_API_KEY=your_key_here
  ```
2. Document the same name in `**.env.example**` (commented) so others know the variable exists.
3. In the plugin:
  ```python
   import os

   def run_plugin(ctx: PluginContext) -> None:
       key = (os.environ.get("YANDEX_SEARCH_API_KEY") or "").strip()
       if not key:
           raise RuntimeError("Set YANDEX_SEARCH_API_KEY in .env")
       # use key in httpx/requests to Yandex Cloud Search or your chosen API
  ```

**Note:** Built-in keys like `YANDEX_API_KEY` are already used for voice in `config`; pick **distinct names** for plugin-specific keys (e.g. `YANDEX_SEARCH_API_KEY`) to avoid confusion.

**Advanced:** To inject into the global YAML tree automatically, you would extend `core/secrets_loader.py` — only needed if you want `ctx.config["my_plugin"]["api_key"]` filled from env without manual `os.environ` in the plugin. Most authors use `os.environ.get(...)` in the plugin only.

---

## Tutorial: Hello World plugin

### Step 1 — Create a folder

```text
interfaces/my_hello_plugin/
```

Use a unique folder name.

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

`NeyraAgent.chat` is **async**. Use `asyncio.run`. For non-Discord modes, `ctx.agent` is usually `None` — use `NeyraAgent(ctx.config)`.

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

The shipped **000EXAMPLE** template stays **enabled: false** and has no **cli_modes** so it never collides.

---

## Reference: layout & manifest

```text
interfaces/000EXAMPLE/
  plugin.yaml
  HELP.md
  HELP-RU.md
  core/
    main.py
```

Shipped: `discord_text/`, `internal_api/`, `local_voice/`, `laptop_screen/`.

### `plugin.yaml` fields


| Field                            | Meaning                                                |
| -------------------------------- | ------------------------------------------------------ |
| `id`                             | Unique string id.                                      |
| `name`, `description`, `version` | Metadata.                                              |
| `enabled`                        | If `false`, CLI mode for this plugin fails at startup. |
| `lifecycle`                      | `resident` / `on_demand`.                              |
| `cli_modes`                      | Names for `python main.py --mode <name>`.              |
| `main_script`                    | Path to entry `.py` relative to the plugin folder.     |


---

## Reference: `PluginContext` & `run_plugin`

Export:

```python
def run_plugin(ctx: PluginContext) -> None:
    ...
```

- `ctx.root` — repo root.
- `ctx.config` — full YAML after `.env` merge for **global** config.
- `ctx.agent` — set for Discord mode only in stock `main.py`; else build `NeyraAgent(ctx.config)` if needed.

---

## How `main.py` wires CLI modes

1. CLI parses `--mode <name>`.
2. `PluginLoader.manifest_for_cli_mode(mode)` finds the manifest whose `cli_modes` list contains that name (values are normalized to lowercase in manifests).
3. If no manifest is found or `enabled` is `false`, startup exits with an error.
4. `import_plugin_module(manifest)` loads and executes the `main_script` file.
5. `run_plugin_entrypoint(module, ctx)` invokes your `run_plugin(ctx)`.

Chain: manifest → load module → `run_plugin(ctx)`.

---

## Loader API

`**core/plugin_loader.py`** — class `**PluginLoader`** (construct with project root, same as `main.py`: `PluginLoader(project_root)`).


| Method                            | Purpose                                                                                              |
| --------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `discover_manifests()`            | All `PluginManifest` objects from `interfaces/*/plugin.yaml`.                                        |
| `list_plugins()`                  | List of dicts for UI/API: id, name, version, enabled, lifecycle, cli_modes, main_script, plugin_dir. |
| `cli_mode_index()`                | Map `mode string → manifest` (duplicate modes log a warning).                                        |
| `manifest_for_cli_mode(mode)`     | Single manifest or `None`.                                                                           |
| `import_plugin_module(manifest)`  | Load `main_script` (for running or debugging).                                                       |
| `load_enabled_modules()`          | Load enabled plugins respecting `lifecycle` (`on_demand` is skipped on this preload pass).           |
| `set_enabled(plugin_id, enabled)` | Persist `enabled` in the matching `plugin.yaml`.                                                     |


`**core/plugin_sdk.py`:**


| Name                                 | Purpose                                               |
| ------------------------------------ | ----------------------------------------------------- |
| `PluginContext`                      | Dataclass: `root`, `config`, `agent`.                 |
| `run_plugin_entrypoint(module, ctx)` | Find and call `run_plugin(ctx)` on the loaded module. |


---

## Reference implementations


| Path                                        | Role                                      |
| ------------------------------------------- | ----------------------------------------- |
| `interfaces/discord_text/`                  | Discord; uses injected `ctx.agent`.       |
| `interfaces/internal_api/`                  | FastAPI; own `NeyraAgent` in `build_app`. |
| `interfaces/local_voice/`, `laptop_screen/` | Stubs.                                    |


---

## Checklist before sharing your plugin

- No secrets in git — document env var names in `.env.example`.
- Unique `id` and `cli_modes`.
- Optional `config.example.yaml` for plugin-local settings.
- Assistant replies via `NeyraAgent` unless you document an exception.

---

## Troubleshooting

**No plugin for mode / “No plugin registers cli_mode”**

- Check spelling in `cli_modes` and that the plugin has `**enabled: true`**.
- Run from the **repository root** (where `main.py` lives).

**Import errors (`ModuleNotFoundError`, `No module named 'core'`)**

- Start with `python main.py --mode …` from the project root, not from inside `interfaces/`.
- Imports expect the usual layout: `from core...`, `from interfaces...`.

`**ctx.agent` is `None`**

- Expected for modes **other than Discord** in stock `main.py` (only Discord injects an agent).
- Create one in the plugin: `NeyraAgent(ctx.config)` (same idea as `internal_api`).

**Duplicate `cli_modes` warning**

- Two manifests registered the same mode string; rename your mode or disable the other plugin.

**Env var empty / “key not set”**

- `.env` missing, wrong variable name, or typo — align code, `.env`, and `.env.example`.

**Plugin does not show up in discovery**

- Path must be exactly `interfaces/<folder>/plugin.yaml` (one level under `interfaces/`).

