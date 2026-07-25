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
4. Shrink 1B/1R flat shims only after callers migrate; **final checklist item: delete duplicate files left in `core/` root**.

### Landed shelves

```
core/agent/
  __init__.py, neyra.py (~2k)
  reply_postprocess.py, micro_plan.py, prompts.py
  people_context.py, speakers.py, turn_events.py, chat_log.py
  tool_heuristics.py

core/reflection/          # ReflectionEngine
core/tools/               # builtins.py → ALL_TOOLS / init_tools

core/memory/
  working_memory.py, emotional_layer.py, ltm_maintenance.py  (+ Hub)

core/runtime/
  mcp_client.py, backup.py   # + server/health/secrets/win
```

Transitional flat shims still in `core/` root (to remove in task 7):
`working_memory.py`, `emotional_layer.py`, `ltm_maintenance.py`, `mcp_client.py`, `backup_manager.py`, plus 1B shims (`plugin_*`, `llm_*`, `server`, `stt`, …).

## Consequences

- Prefer canonical imports (`core.tools`, `core.runtime.mcp_client`, `core.runtime.backup`, `core.memory.*`).
- Next: further shrink `neyra.py`, crutch audit, then delete root duplicates (task 7) + acceptance.
