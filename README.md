# Neyra - AIAssist

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

- `model` mode (console/core runtime),
- `discord_text` interface (text + image flow).

## Architecture at a glance

- `core/` - model, memory, reflection, tools, secrets loader.
- `core/voice/` - voice adapters and factories (cloud/local evolution path).
- `interfaces/` - pluggable runtimes (`discord_text`, local voice stub, screen stub).
- `scripts/` - ops helpers (health checks and maintenance utilities).
- `main.py` - app entrypoint and mode launcher.
- `run_neyra.bat` - Windows launcher with mode selection and preflight.

## Product direction

Neyra is moving toward a public personal-assistant platform:

- desktop assistant app (OS command automation with strict safety controls),
- mobile-lite chat client via API,
- micro web dashboard with status, controls, and API docs,
- external storage adapters (Google Drive-first) for backup/restore,
- modular expansion (voice/screen/music/plugins).

Long-term hardware "assistant station" form factor is tracked as a future backlog item.

## Quick start (Windows)

1. Create and activate venv:
  - `python -m venv .venv`
  - `.venv\Scripts\activate`
2. Install dependencies:
  - `pip install -r requirements.txt`
3. Create `.env` from `.env.example` and fill secrets.
4. Create `config.yaml` from `config.example.yaml` and adjust runtime values.
5. Run preflight check:
  - `.venv\Scripts\python.exe scripts\healthcheck.py`
6. Run app:
  - `run_neyra.bat`
  - or direct: `.venv\Scripts\python.exe main.py --mode model`

## Run modes

- `model` - console mode (default).
- `discord` - Discord text bot.
- `local_voice` - local voice interface stub.
- `screen` - laptop screen interface stub.

## Environment variables

See `.env.example`.

Required for cloud model:

- `OPENROUTER_API_KEY`

Required only for Discord mode:

- `DISCORD_TOKEN`

Optional (future voice integrations):

- `DEEPGRAM_API_KEY`
- `GROQ_API_KEY`
- `YANDEX_API_KEY`
- `YANDEX_FOLDER_ID`

## Configuration files

- Public template: `config.example.yaml`
- Local private runtime config: `config.yaml` (ignored by git)
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

## Notes

- Voice bot in Discord VC is intentionally not part of current stable runtime.
- Runtime logs and memory artifacts are ignored by git (see `.gitignore`).

## Support the project

Neyra is an independent open-source effort: inference APIs, embedding models, hosting for demos, and sustained development all have a real cost. If the project is useful to you, consider supporting it—any amount helps keep the core free and moving forward.

### Why donate

- **API and infrastructure:** cloud LLM calls, optional voice providers, backups, and test environments add up over time.
- **Time:** design, security review, documentation, and community support are ongoing work alongside feature development.
- **Independence:** voluntary support reduces pressure to gate core features or ship low-quality integrations just to monetize.

### How we use support

Funds typically go toward: API bills for development and CI-related checks, domain/hosting if we add a public demo or docs site, and occasionally hardware for local-model testing. There is no corporate backing behind this repository—transparency is the default.

### Ways to support

- **GitHub Sponsors** — recurring or one-time tips tied to this repo (add your maintainer profile link when available).
- **One-time tips** — platforms such as Ko-fi, Boosty, or similar (links can be published in repo wiki or pinned issue when set up).
- **Cryptocurrency** — if offered, addresses will be listed only in verified project channels (README or releases), never via unsolicited DMs.

**Security:** never send money or secrets to anyone claiming to represent the project without verifying it is the official repository (`https://github.com/KORESHon/Neyra-AIAssist`) and official links from this README.

### What you get

The MIT-licensed core stays open regardless of donations. Support is voluntary and does not unlock proprietary “premium” core code here—though future optional add-ons, if any, may be documented separately.

### Contact

For sponsorship questions or to propose institutional support, open a discussion on GitHub or contact the maintainer through the profile linked from the repository.

## License

MIT (see `LICENSE`).