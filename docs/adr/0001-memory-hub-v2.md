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

## Timestamps / timezone

- **Storage:** Hub SQLite `ts` / `created_at` columns are always **UTC ISO** (with offset), so `ORDER BY ts` stays chronological across hosts and after TZ changes. Incoming values are normalized via `core.timeutil.to_utc_iso`.
- **Wall clock:** reflection windows, WM labels, and `get_current_time` use the **host OS timezone** by default. Optional override: `system.timezone` (IANA, e.g. `Europe/Moscow`) via `configure_timezone`.
- **Readers:** convert with `to_local()`; do not early-`break` on TEXT order when filtering windows (mixed legacy offsets possible during migration).

## RAG write policy

Config `memory.rag_write_mode`: `off` | `digest` | `important_only`.  
Raw full-chat embed on every turn is **forbidden** (Hub `save_dialog_semantic` no-ops).  
Escape hatch for migration only: `legacy_dialog`.  
Knowledge / important fragments still go through `remember_knowledge` (unless `off`).

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

## Cutover (done)

The `hub_legacy_import` / `hub_legacy_fallback` / `hub_dual_write_legacy` config flags have been
**removed entirely** — Hub SQLite is now the sole store for people/diary/journal/WM whenever a
`MemoryHub` is attached (no JSON/JSONL/MD writes, no fallback reads). Two things remain by design:

- `run_hub_legacy_import()` + `POST /v1/memory/import-legacy` (admin) for manual/one-off imports.
- An automatic, marker-gated one-shot import at startup when Hub SQLite is empty but legacy
  files are still found on disk (safety net for upgrades/restores, not a permanent mode).

`PeopleDB` / `NeyraDiary` / `ReflectionEngine` / working-memory helpers remain as thin read/write
wrappers around Hub; they only touch the filesystem when no `MemoryHub` is attached at all
(console/emergency use).

## Consequences

- Agents, Internal API `/v1/memory/*`, tools (`recall_chat`, `search_memory`, …), MCP debug, and dashboard must talk to Hub.
- Prompt injection (people / diary / WM / semantic) goes through Hub only; no legacy-file fallback once a Hub is attached.
- Phase 1B may rearrange packages; import shims stay stable (`from core.memory import …`).
