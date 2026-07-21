# ADR-0001 — Memory Hub v2 (SQLite truth + Chroma semantic index)

**Status:** Accepted (Phase 1A in progress)  
**Date:** 2026-07-21  
**Context:** `PLAN.md` Stage 1 / Phase 1A

## Decision

Neyra uses a single **MemoryHub** facade (`core/memory/`) as the only entry point for durable memory and prompt injection of memory sections.

| Layer | Store | Role |
|-------|--------|------|
| Dialog truth | SQLite `chat_log` | Full turns (who / what / when / where / meta) |
| Structured truth | SQLite tables | people, diary, journal, working memory |
| Semantic index | Chroma (adapter) | Only recallable content by `metadata.type` |
| STM | RAM (+ optional view of last N from `chat_log`) | Active window |

## Concurrency

One writer contour per process: sync `sqlite3` with a process-wide `threading.RLock`, WAL mode. Async callers use `asyncio.to_thread` for Hub writes. No parallel SQLite writers from plugins.

## RAG write policy

Config `memory.rag_write_mode`: `off` | `digest` | `important_only`.  
Raw full-chat embed on every turn is **forbidden** after cutover. Until layers fully migrate, dual-write may still call legacy LTM `save` behind a compatibility flag; Hub remains source of truth for chronology via `chat_log`.

## Events

| Event | Meaning |
|-------|---------|
| `memory.short_term_update` | STM size / window changed |
| `memory.long_term_write` | Semantic index write (not chat_log) |
| `memory.chat_log_append` | Row(s) appended to SQLite chat_log |
| `memory.journal_updated` | Journal row changed |
| `memory.working_memory_updated` | WM snapshot changed |

## Vector backend seam

`SemanticIndex` protocol + Chroma adapter. Future sqlite-vss (Stage 4) plugs in without changing agent call sites.

## Cutover

After Phase 1A green: json/jsonl/md people/diary/journal/WM are not primary. Optional one-shot `memory.hub_legacy_import`, then `false`.

## Consequences

- Agents, Internal API `/v1/memory/*`, tools (`recall_chat`, `search_memory`, …), MCP debug, and dashboard must talk to Hub.
- Phase 1B may rearrange packages; import shims stay stable (`from core.memory import …`).
