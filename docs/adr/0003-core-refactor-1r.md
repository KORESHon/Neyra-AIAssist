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

### First slice (landed)

```
core/agent/
  __init__.py          # exports NeyraAgent + constants
  neyra.py             # NeyraAgent orchestration (still large)
  reply_postprocess.py # sound tags / think blocks / empty salvage
  micro_plan.py        # PLAN stream filters
  prompts.py           # talk + brain system prompt builders
```

## Consequences

- Callers keep `from core.agent import NeyraAgent`.
- Further slices: `prompts.py`, `chat.py`, `memory_ops.py`, then `reflection` / `tools` / WM packages.
- Prefer small reviewable commits per shelf.
