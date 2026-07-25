# ADR 0003 — Core refactor Phase 1R

## Status

Accepted (in progress on `feat/core-refactor-1r` / PR #7).

## Context

Phase 1B moved modules into packages with compat shims. Phase 1R splits monoliths and removes transitional duplicates.

## Decision

1. Inventory → shelves (see `PLAN.md` 1R map).
2. Split by responsibility; keep public APIs (`from core.agent import NeyraAgent`, `from core.reflection import ReflectionEngine`).
3. Audit crutches found during moves.
4. **Delete flat shim duplicates** in `core/` root after callers use canonical imports.

### Landed

```
core/agent/     # neyra + shelves (llm_setup, turn_prep, turn_finalize, …)
core/reflection/
core/tools/
core/memory/    # hub + WM + emotional_layer + ltm_maintenance + …
core/runtime/   # server, health, secrets, win, mcp_client, backup
core/llm/
core/plugins/
core/voice/
```

Root `core/` keeps only non-duplicate thin modules (`event_bus`, `identity`, `timeutil`, `vision_util`, `external_storage`, …).

Removed shims include: `plugin_*`, `llm_profile`, `llm_retry`, `server`, `stt`, `yandex_tts`, `working_memory`, `emotional_layer`, `ltm_maintenance`, `mcp_client`, `backup_manager`, `secrets_loader`, `health_monitor`, `win_runtime`, `openrouter_balance`.

## Consequences

- Import only canonical package paths.
- Remaining work: shrink chat/stream bodies in `neyra.py`, finish acceptance (Discord stand), merge PR #7.
