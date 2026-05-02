<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Neyra - AIAssist

AI Assisted

**Repository:** [github.com/KORESHon/Neyra-AIAssist](https://github.com/KORESHon/Neyra-AIAssist)

Modular AI assistant platform with a core-first architecture.

## Overview

Neyra is designed as a reusable assistant core plus pluggable integrations.

Key goals:

- stable core (`LLM + Memory + Reflection + Tools`),
- provider-agnostic model backends (cloud/local),
- event-driven integrations and webhooks,
- plugin-style extensibility without rewriting the core.

Current stable runtime:

- `**python main.py`** — core: HTTP API, web dashboard, one `NeyraAgent`, resident plugins (e.g. Discord when enabled),
- `**python main.py --mode console`** — terminal-only for prompt experiments,
- `discord` (text + music) and other interfaces ship as plugins under `interfaces/`.

### Dashboard (frontend)

Web UI: **React + Vite + Tailwind CSS** under `frontend/`. Production build outputs to `frontend/dist` and is served by Internal API (`npm install && npm run build` before shipping).

### MCP debug (IDE tooling)

Optional **Model Context Protocol** debug server in `tools/mcp_server/` (stdio MCP for Cursor): tail logs, issue Internal API requests, inject Event Bus events (`POST /v1/debug/fire_event`), inspect memory snapshots. Configure via `docs/en/setup/mcp-debug-server.md`.

### Discord and music

Single resident plugin **`interfaces/discord/`** (text gateway + music service). Music path uses **Lavalink 4.x** with up-to-date **YouTube / source plugins**; deployments often set Lavalink client identifiers such as **ANDROID_VR** where needed to avoid provider-side breakage.

### Models (examples)

Fully driven by `config.yaml`. Typical stacks pair large **MoE** chat models (e.g. **Qwen3 235B** class through OpenRouter) with heavier models for reflection/diary analysis (e.g. **gpt-oss-120b** class). Swap IDs to match your provider and quota.

## Architecture at a glance

- `core/` - model, memory, reflection, tools, secrets loader.
- `core/voice/` - voice adapters and factories (cloud/local evolution path).
- `frontend/` - React+Vite+Tailwind sources; production bundle in `frontend/dist`.
- `interfaces/` - plugins (`interfaces/<id>/plugin.yaml` + `main.py`); shipped: **`discord`** (unified text+music), `internal_api`, `local_voice`, `laptop_screen`; template `**000EXAMPLE/`** (see Plugin SDK links below).
- `scripts/` - ops helpers (health checks and maintenance utilities).
- `main.py` — entrypoint (`core` vs `console` only).
- `run_neyra.bat` — Windows menu (core / console / preflight).
- `run_neyra.sh` — Linux/macOS menu (core / console / status / stop / git updates).

## Product direction

Neyra is moving toward a public personal-assistant platform:

- desktop assistant app (OS command automation with strict safety controls),
- mobile-lite chat client via API,
- micro web dashboard with status, controls, and API docs,
- external storage adapters (Google Drive-first) for backup/restore,
- modular expansion (voice/screen/music/plugins).

Long-term hardware "assistant station" form factor is tracked as a future backlog item.

## Quick start

1. Create and activate venv:
  - `python -m venv .venv`
  - Windows: `.venv\Scripts\activate`
  - Linux/macOS: `source .venv/bin/activate`
2. Install dependencies:
  - `pip install -r requirements.txt`
3. Create `.env` from `.env.example` and fill secrets.
4. Create `config.yaml` from `config.example.yaml` and adjust runtime values.
5. Copy plugin templates where needed:
   - `interfaces/discord/config.example.yaml` → `interfaces/discord/config.yaml`
   - `interfaces/internal_api/config.example.yaml` → `interfaces/internal_api/config.yaml`
   - other plugins: `interfaces/<id>/config.example.yaml` → `interfaces/<id>/config.yaml`
6. Preflight (example): `python scripts/healthcheck.py --mode console --skip-http`
7. Run:
  - Windows: `run_neyra.bat`
  - Linux/macOS: `chmod +x run_neyra.sh && ./run_neyra.sh`
  - Direct: `python main.py` (core) or `python main.py --mode console`

## Run modes (CLI)

- `**core`** (default) — HTTP API, dashboard, resident plugins.
- `**console**` — terminal chat only.

Plugins start **with** the core from root `config.yaml`, optional per-plugin `interfaces/<id>/config.yaml`, and `**plugin.yaml`** (enable/disable and lifecycle only there). There is no separate `--mode discord` CLI.

## Environment variables

See `.env.example`.

Required for cloud model:

- `OPENROUTER_API_KEY`

Required when `discord` is enabled in `interfaces/discord/plugin.yaml`:

- `DISCORD_TOKEN` in `.env` (optional legacy: `discord.token` merged from old configs)

Optional (future voice integrations):

- `DEEPGRAM_API_KEY`
- `GROQ_API_KEY`
- `YANDEX_API_KEY`
- `YANDEX_FOLDER_ID`

## Configuration files

- Public template: `config.example.yaml`
- Local private runtime config: `config.yaml` (ignored by git)
- Plugin settings: `interfaces/<plugin_id>/config.yaml` (optional; copy from `config.example.yaml` in that folder). HTTP bind + dashboard: `interfaces/internal_api/config.yaml`.
- Secret values: `.env` (ignored by git)

## System prompts and behavior tuning

Primary places to edit prompt behavior:

- Base assistant prompt (main personality/instructions):
  - `config.yaml` -> `assistant.system_prompt`
- Final system prompt assembly (injects memory, tools, web context, vision rules):
  - `core/agent.py` (`_build_system_prompt`)
- Reflection prompts (nightly and hourly diary analysis):
  - `core/reflection.py` (`_analyze_diary_json`, `hourly_diary_note`)
- Tool behavior and tool-facing descriptions:
  - `core/tools.py`
- Memory-trigger and web-trigger heuristics that affect prompt context:
  - `core/agent.py` (`_collect_tool_context`, `_handle_websearch_trigger`)

Recommendation:

- Keep production persona details only in local `config.yaml`.
- Keep `config.example.yaml` generic for public repository sharing.

## Planning and documentation files

- `README.md` - public product/technical overview (English).
- `README-RU.md` - public product/technical overview (Russian).
- `PLAN.md` - roadmap (when tracked in the repo).
- `docs/en/README.md` / `docs/ru/README.md` - documentation index (architecture, setup, API, ops, usage, plugins, MCP, Web UI).
- **Plugin SDK (tutorial & reference)** — [HELP.md (English)](interfaces/000EXAMPLE/HELP.md) · [HELP-RU.md (Русский)](interfaces/000EXAMPLE/HELP-RU.md).

## Notes

- Voice bot in Discord VC is intentionally not part of current stable runtime.
- Runtime logs and memory artifacts are ignored by git (see `.gitignore`).

## Support the project

If you like Neyra and want to support its development (or just buy the author a coffee), you can send cryptocurrency. The addresses below match wallets used in Trust Wallet and Telegram (TG) Wallet.

- **TON (network: TON):** `UQD6p87_YQNeZmGduBHnkWBF3AbvyNOwt_xt8fn1Vd3zBSYa`
- **USDT (network: TON):** `UQD6p87_YQNeZmGduBHnkWBF3AbvyNOwt_xt8fn1Vd3zBSYa`
- **USDT (network: TRC20):** `TU467q2tsQLH58u6KVh3LyGwx7sqn2WyPQ`
- **USDT (network: ERC20):** `0xf834f04668b947eeb56b433c54173f311a06392a`
- **ETH (Ethereum Mainnet):** `0xf834f04668b947eeb56b433c54173f311a06392a`
- **BTC (Bitcoin Network):** `bc1qevu7yty2l4u3n54gjkvj9nrtypj303ejd7e0z3`

*Always verify the network before sending. Thank you for your support 🚀*

The core stays open source under the MIT license regardless of donations.

## AI-assisted development

This project is a practical exploration of **prompt engineering** and how complex AI systems can be steered in a real codebase.

- **Architecture, system design, and module integration** are intentionally driven by a human.
- **Routine code, scaffolding, and much of the implementation** were written with heavy use of AI coding agents (Cursor, LLM assistants).

I believe the future of building software is the synergy between a human **architect** and AI-assisted **implementation**. If you find rough or suboptimal generated patches, open an Issue or a PR—reviews from experienced developers are genuinely welcome.

## License

MIT (see `LICENSE`).