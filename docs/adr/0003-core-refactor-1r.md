# ADR 0003 — Core refactor Phase 1R

## Status

Accepted (merged via [PR #7](https://github.com/KORESHon/Neyra-AIAssist/pull/7), `1b873d0`, 2026-07-25).

## Context

Phase 1B introduced packages with flat shims. Phase 1R splits monoliths and makes `core/` readable: packages plus one orchestrator module.

## Decision

1. **Single top-level module:** `core/neyra.py` holds `NeyraAgent` (main control plane).
2. **Helpers** live in `core/agent/` (prompts, turn prep/finalize, heuristics, …) — not a second orchestrator file.
3. **Everything else** is a package: `memory`, `llm`, `plugins`, `runtime`, `reflection`, `tools`, `voice`.
4. Former root utilities moved into packages:
   - `event_bus`, `identity`, `timeutil`, `external_storage` → `core/runtime/`
   - `vision_util` → `core/voice/`
5. Flat 1B/1R shims deleted; canonical imports only.
6. `from core.agent import NeyraAgent` remains as a lazy re-export; preferred: `from core.neyra import NeyraAgent`.

### Target root

```
core/
  __init__.py
  neyra.py          # only non-package module
  agent/ llm/ memory/ plugins/ reflection/ runtime/ tools/ voice/
```

## Consequences

- Clear entry point for the agent brain.
- Talk lanes live in `core/agent/chat.py` and `core/agent/chat_stream.py`; `neyra.py` stays thin wrappers + wiring.
- Acceptance 2026-07-25: offline smokes, Auto Review, MCP `/v1/chat`, WS `chat_stream`, Discord UX smoke.
