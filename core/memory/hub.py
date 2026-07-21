"""MemoryHub — single facade for durable memory (Phase 1A)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from core.event_bus import (
    MEMORY_CHAT_LOG_APPEND,
    MEMORY_JOURNAL_UPDATED,
    MEMORY_LONG_TERM_WRITE,
    MEMORY_WORKING_MEMORY_UPDATED,
    CoreEvent,
)
from core.memory.semantic_index import ChromaSemanticIndex, SemanticIndex
from core.memory.sqlite_store import SqliteStore

logger = logging.getLogger("neyra.memory.hub")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryHub:
    """
    Source of truth for chat_log + structured layers in SQLite.
    Semantic index via adapter. Legacy JSON/JSONL dual-write remains until full cutover.
    """

    def __init__(
        self,
        config: dict[str, Any],
        *,
        long_memory: Any = None,
        event_bus: Any = None,
        semantic: Optional[SemanticIndex] = None,
    ):
        mem = config.get("memory") if isinstance(config.get("memory"), dict) else {}
        self.config = config
        self.mem_cfg = mem
        self.event_bus = event_bus
        self._long_memory = long_memory
        path = str(mem.get("sqlite_path") or "./memory/neyra_memory.db")
        self.sqlite = SqliteStore(path)
        self.rag_write_mode = str(mem.get("rag_write_mode") or "important_only").strip().lower()
        if self.rag_write_mode not in {"off", "digest", "important_only", "legacy_dialog"}:
            logger.warning("Unknown rag_write_mode=%r — using important_only", self.rag_write_mode)
            self.rag_write_mode = "important_only"
        if semantic is not None:
            self.semantic: SemanticIndex = semantic
        elif long_memory is not None:
            self.semantic = ChromaSemanticIndex(long_memory)
        else:
            self.semantic = ChromaSemanticIndex(_NullLTM())
        logger.info(
            "MemoryHub ready | sqlite=%s | schema_v%s | rag_write_mode=%s",
            path,
            self.sqlite.schema_version(),
            self.rag_write_mode,
        )

    def close(self) -> None:
        self.sqlite.close()

    def new_turn_id(self) -> str:
        return str(uuid.uuid4())

    def allows_raw_dialog_embed(self) -> bool:
        """
        Raw full-chat Chroma embeds are forbidden for off/digest/important_only.
        Escape hatch: rag_write_mode=legacy_dialog (migration only).
        """
        return self.rag_write_mode == "legacy_dialog"

    def append_chat(
        self,
        *,
        role: str,
        text: str,
        user_id: Optional[str] = None,
        display_name: Optional[str] = None,
        channel_id: Optional[str] = None,
        source: Optional[str] = None,
        turn_id: Optional[str] = None,
        latency_ms: Optional[float] = None,
        emotion: Optional[str] = None,
        mood: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        ts: Optional[str] = None,
        publish_event: bool = True,
    ) -> int:
        ids = self.append_chat_batch(
            [
                {
                    "role": role,
                    "text": text,
                    "user_id": user_id,
                    "display_name": display_name,
                    "channel_id": channel_id,
                    "source": source,
                    "turn_id": turn_id,
                    "latency_ms": latency_ms,
                    "emotion": emotion,
                    "mood": mood,
                    "meta": meta,
                    "ts": ts,
                }
            ],
            publish_event=publish_event,
        )
        return ids[0] if ids else 0

    def append_chat_batch(
        self,
        rows: list[dict[str, Any]],
        *,
        publish_event: bool = True,
    ) -> list[int]:
        prepared: list[dict[str, Any]] = []
        for row in rows:
            prepared.append(
                {
                    **row,
                    "ts": row.get("ts") or _utc_now_iso(),
                    "text": str(row.get("text") or ""),
                    "role": str(row.get("role") or ""),
                }
            )
        ids = self.sqlite.append_chat_rows(prepared)
        if publish_event and self.event_bus is not None and ids:
            try:
                first = prepared[0]
                self.event_bus.publish(
                    CoreEvent(
                        MEMORY_CHAT_LOG_APPEND,
                        "core.memory.hub",
                        {
                            "ids": ids,
                            "count": len(ids),
                            "turn_id": first.get("turn_id"),
                            "user_id": first.get("user_id"),
                            "channel_id": first.get("channel_id"),
                            "roles": [r.get("role") for r in prepared],
                        },
                    )
                )
            except Exception as e:
                logger.debug("chat_log_append event failed: %s", e)
        return ids

    def list_chat(
        self,
        *,
        user_id: Optional[str] = None,
        channel_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        newest_first: bool = True,
    ) -> list[dict[str, Any]]:
        return self.sqlite.list_chat(
            user_id=user_id,
            channel_id=channel_id,
            limit=limit,
            offset=offset,
            newest_first=newest_first,
        )

    def search_semantic(self, query: str, n_results: Optional[int] = None) -> list[str]:
        if not getattr(self.semantic, "rag_enabled", True):
            return []
        return self.semantic.search(query, n_results=n_results)

    def remember_knowledge(
        self, text: str, metadata: Optional[dict[str, Any]] = None
    ) -> tuple[bool, str]:
        if self.rag_write_mode == "off":
            return False, "rag_write_mode=off"
        meta = dict(metadata or {})
        if "type" not in meta:
            meta["type"] = "knowledge"
        ok, info = self.semantic.add_knowledge(text, meta)
        if ok and self.event_bus is not None:
            try:
                self.event_bus.publish(
                    CoreEvent(
                        MEMORY_LONG_TERM_WRITE,
                        "core.memory.hub",
                        {"kind": "knowledge", "id": info, "rag_write_mode": self.rag_write_mode},
                    )
                )
            except Exception as e:
                logger.debug("long_term_write event failed: %s", e)
        return ok, info

    def save_dialog_semantic(
        self, user_msg: str, assistant_msg: str, metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Raw dialog embed — only when rag_write_mode=legacy_dialog."""
        if not self.allows_raw_dialog_embed():
            logger.debug(
                "Skip raw dialog Chroma embed (rag_write_mode=%s)", self.rag_write_mode
            )
            return False
        if self._long_memory is None:
            return False
        self._long_memory.save(user_msg, assistant_msg, metadata)
        return True

    # ── people / diary / journal / WM ─────────────────────────────────────────

    def upsert_person(
        self,
        person_id: str,
        *,
        display_name: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        self.sqlite.upsert_person(
            person_id=person_id,
            display_name=display_name,
            aliases=aliases,
            meta=meta,
        )

    def add_person_fact(
        self,
        person_id: str,
        fact: str,
        *,
        emotion_note: Optional[str] = None,
        source: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        person_meta: Optional[dict[str, Any]] = None,
        aliases: Optional[list[str]] = None,
        display_name: Optional[str] = None,
    ) -> int:
        if person_meta or aliases or display_name:
            self.upsert_person(
                person_id,
                display_name=display_name,
                aliases=aliases,
                meta=person_meta,
            )
        else:
            # ensure row exists for FK
            if self.sqlite.get_person(person_id) is None:
                self.upsert_person(person_id, display_name=display_name or person_id)
        return self.sqlite.add_person_fact(
            person_id=person_id,
            fact=fact,
            emotion_note=emotion_note,
            source=source,
            meta=meta,
        )

    def get_person(self, person_id: str) -> Optional[dict[str, Any]]:
        return self.sqlite.get_person(person_id)

    def list_person_facts(self, person_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.sqlite.list_person_facts(person_id, limit=limit)

    def add_diary_note(
        self,
        text: str,
        *,
        source: Optional[str] = None,
        emotion: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> int:
        return self.sqlite.add_diary_note(
            text=text, source=source, emotion=emotion, meta=meta, ts=ts
        )

    def list_diary_notes(self, *, limit: int = 20, newest_first: bool = True) -> list[dict[str, Any]]:
        return self.sqlite.list_diary_notes(limit=limit, newest_first=newest_first)

    def add_journal_entry(
        self,
        text: str,
        *,
        title: Optional[str] = None,
        kind: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        ts: Optional[str] = None,
        publish_event: bool = True,
    ) -> int:
        row_id = self.sqlite.add_journal_entry(
            text=text, title=title, kind=kind, meta=meta, ts=ts
        )
        if publish_event and self.event_bus is not None:
            try:
                self.event_bus.publish(
                    CoreEvent(
                        MEMORY_JOURNAL_UPDATED,
                        "core.memory.hub",
                        {"id": row_id, "kind": kind, "title": title},
                    )
                )
            except Exception as e:
                logger.debug("journal_updated event failed: %s", e)
        return row_id

    def save_wm_snapshot(
        self,
        content: str,
        *,
        user_id: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        ts: Optional[str] = None,
        publish_event: bool = True,
    ) -> int:
        row_id = self.sqlite.save_wm_snapshot(
            user_id=user_id, content=content, meta=meta, ts=ts
        )
        if publish_event and self.event_bus is not None:
            try:
                self.event_bus.publish(
                    CoreEvent(
                        MEMORY_WORKING_MEMORY_UPDATED,
                        "core.memory.hub",
                        {"id": row_id, "user_id": user_id, "chars": len(content or "")},
                    )
                )
            except Exception as e:
                logger.debug("wm_updated event failed: %s", e)
        return row_id

    def stats(self) -> dict[str, Any]:
        return {
            "sqlite_path": str(self.sqlite.path),
            "schema_version": self.sqlite.schema_version(),
            "rag_write_mode": self.rag_write_mode,
            "allows_raw_dialog_embed": self.allows_raw_dialog_embed(),
            "chat_log": self.sqlite.count_table("chat_log"),
            "people": self.sqlite.count_table("people"),
            "person_facts": self.sqlite.count_table("person_facts"),
            "diary_notes": self.sqlite.count_table("diary_notes"),
            "journal_entries": self.sqlite.count_table("journal_entries"),
            "working_memory_snapshots": self.sqlite.count_table("working_memory_snapshots"),
            "semantic_outbox": self.sqlite.count_table("semantic_outbox"),
            "chroma_records": self.semantic.count(),
            "rag_enabled": bool(getattr(self.semantic, "rag_enabled", True)),
        }


class _NullLTM:
    rag_enabled = False

    def search(self, query: str, n_results: Optional[int] = None) -> list[str]:
        return []

    def count(self) -> int:
        return 0

    def add_knowledge(self, text: str, metadata: Optional[dict] = None) -> tuple[bool, str]:
        return False, "no long_memory"

    def save(self, user_msg: str, assistant_msg: str, metadata: Optional[dict] = None) -> None:
        return None
