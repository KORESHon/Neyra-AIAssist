# ADR 0002 — Core layout (Phase 1B)

## Status

Accepted (in progress on `feat/core-layout-1b`).

## Context

After Memory Hub 1A, `core/` still had many flat modules (`plugin_*`, `llm_*`, `server`, `stt`, …). Phase 1B packages them without changing runtime behavior.

## Decision

Canonical packages:

| Package | Responsibility |
|---------|----------------|
| `core.memory` | Hub, SQLite, Chroma adapter, STM/People/Diary helpers (`stores`) |
| `core.plugins` | Plugin loader / config / SDK / builder (plugin_manager) |
| `core.llm` | OpenAI-compatible profile, retries, OpenRouter usage |
| `core.runtime` | HTTP server entry, health, Windows patches, secrets |
| `core.voice` | STT / Yandex TTS |

**Compat shims:** flat modules (`core.plugin_loader`, `core.llm_profile`, `core.server`, `core.stt`, `core.memory.legacy`, …) re-export from the packages for one release.

**Lazy package exports:** package `__init__` must not eagerly import heavy HTTP stacks. Prefer submodule imports (`from core.runtime.secrets import …`). Public names that need the heavy module use lazy `__getattr__`.

## Consequences

- Callers can migrate to canonical imports gradually.
- Light scripts (`healthcheck`, secrets loading) stay free of FastAPI / plugin builder / OpenRouter client at import time.
- Optional later: split `core/agent.py` into `core/agent/` without API changes.
