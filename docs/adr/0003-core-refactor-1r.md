# ADR 0003 — Core refactor Phase 1R

## Status

Accepted (in progress on `feat/core-refactor-1r` / PR #7).

## Context

Phase 1B moved modules into packages (`plugins`, `llm`, `runtime`, `voice`, `memory.stores`) with compat shims. Large orchestration files (especially `agent.py` ~2.6k lines) remained monoliths.

## Decision

Phase **1R** deep-refactors for readability without product behavior changes:

1. Inventory monoliths → target shelves (see `PLAN.md` 1R map).
2. Split by responsibility into packages/modules; keep public imports stable (`from core.agent import NeyraAgent`).
3. Audit crutches/bugs found during moves; fix or document.
4. Shrink 1B flat shims only after callers migrate.

### Landed shelves

```
core/agent/
  __init__.py          # exports NeyraAgent + constants
  neyra.py             # NeyraAgent orchestration (~2.2k; still large)
  reply_postprocess.py # sound tags / think blocks / empty salvage
  micro_plan.py        # PLAN stream filters
  prompts.py           # talk + brain system prompt builders
  people_context.py    # people mention / dossier blocks
  speakers.py          # speaker labels / spoken user lines
  turn_events.py       # Event Bus publish helpers for turns
  chat_log.py          # Hub chat_log dual-write helper

core/reflection/
  __init__.py          # exports ReflectionEngine
  engine.py            # former core/reflection.py

core/memory/
  working_memory.py    # moved from core/working_memory.py
  emotional_layer.py   # moved from core/emotional_layer.py
  ltm_maintenance.py   # moved from core/ltm_maintenance.py
```

Flat shims kept for transitional imports: `core/working_memory.py`, `core/emotional_layer.py`, `core/ltm_maintenance.py`.

Canonical imports: `from core.memory import working_memory`, `emotional_layer`, `ltm_maintenance`; `from core.reflection import ReflectionEngine`.

## Consequences

- Callers keep `from core.agent import NeyraAgent` and `from core.reflection import ReflectionEngine`.
- Next: `tools` / `mcp_client` / `backup_manager` packages; further shrink `neyra.py`; then shim cleanup + crutch audit.
- Prefer small reviewable commits per shelf.
