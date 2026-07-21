"""SQLite store for Memory Hub v2 (single-writer via RLock + WAL)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.memory.migrations import MIGRATIONS

logger = logging.getLogger("neyra.memory.sqlite")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteStore:
    """Process-local SQLite access. All methods assume the Hub holds the write lock."""

    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we use explicit BEGIN
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            cur = self._conn.execute("SELECT version FROM schema_migrations")
            applied = {int(r[0]) for r in cur.fetchall()}
            for version, sql in MIGRATIONS:
                if version in applied:
                    continue
                logger.info("SQLite migrate → v%s (%s)", version, self.path)
                # executescript auto-commits; do not wrap in BEGIN/COMMIT
                self._conn.executescript(sql)
                self._conn.execute(
                    "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, _utc_now_iso()),
                )

    def append_chat_rows(self, rows: list[dict[str, Any]]) -> list[int]:
        """Insert chat_log rows; returns new ids."""
        ids: list[int] = []
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                for row in rows:
                    meta = row.get("meta")
                    if meta is not None and not isinstance(meta, str):
                        meta = json.dumps(meta, ensure_ascii=False)
                    cur = self._conn.execute(
                        """
                        INSERT INTO chat_log(
                            ts, role, user_id, display_name, channel_id, source,
                            text, turn_id, latency_ms, emotion, mood, meta
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row.get("ts") or _utc_now_iso(),
                            str(row.get("role") or ""),
                            row.get("user_id"),
                            row.get("display_name"),
                            row.get("channel_id"),
                            row.get("source"),
                            str(row.get("text") or ""),
                            row.get("turn_id"),
                            row.get("latency_ms"),
                            row.get("emotion"),
                            row.get("mood"),
                            meta,
                        ),
                    )
                    ids.append(int(cur.lastrowid))
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise
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
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        clauses: list[str] = []
        params: list[Any] = []
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        if channel_id:
            clauses.append("channel_id = ?")
            params.append(channel_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "DESC" if newest_first else "ASC"
        sql = (
            f"SELECT * FROM chat_log {where} "
            f"ORDER BY ts {order}, id {order} LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        with self._lock:
            cur = self._conn.execute(sql, params)
            return [self._row_to_dict(r) for r in cur.fetchall()]

    def count_table(self, table: str) -> int:
        allowed = {
            "chat_log",
            "people",
            "person_facts",
            "diary_notes",
            "journal_entries",
            "working_memory_snapshots",
            "semantic_outbox",
        }
        if table not in allowed:
            raise ValueError(f"count_table: unknown table {table}")
        with self._lock:
            cur = self._conn.execute(f"SELECT COUNT(*) FROM {table}")
            return int(cur.fetchone()[0])

    def schema_version(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            )
            return int(cur.fetchone()[0])

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        meta = d.get("meta")
        if isinstance(meta, str) and meta.strip():
            try:
                d["meta"] = json.loads(meta)
            except Exception:
                pass
        return d
