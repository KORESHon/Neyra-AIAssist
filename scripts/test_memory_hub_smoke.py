#!/usr/bin/env python3
"""Smoke: MemoryHub SQLite chat_log append + list (no Chroma / LLM)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.event_bus import MEMORY_CHAT_LOG_APPEND, EventBus
from core.memory import MemoryHub


def main() -> int:
    events: list[str] = []
    bus = EventBus()
    bus.subscribe(MEMORY_CHAT_LOG_APPEND, lambda e: events.append(e.event_type))

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "neyra_memory.db"
        hub = MemoryHub(
            {"memory": {"sqlite_path": str(db), "rag_write_mode": "off"}},
            event_bus=bus,
        )
        turn = hub.new_turn_id()
        ids = hub.append_chat_batch(
            [
                {
                    "role": "user",
                    "text": "привет",
                    "user_id": "u1",
                    "channel_id": "c1",
                    "source": "smoke",
                    "turn_id": turn,
                },
                {
                    "role": "assistant",
                    "text": "хай",
                    "user_id": "u1",
                    "channel_id": "c1",
                    "source": "smoke",
                    "turn_id": turn,
                },
            ]
        )
        assert len(ids) == 2, ids
        rows = hub.list_chat(user_id="u1", limit=10, newest_first=False)
        assert len(rows) == 2, rows
        assert rows[0]["text"] == "привет"
        assert rows[1]["text"] == "хай"
        st = hub.stats()
        assert st["chat_log"] == 2, st
        assert st["schema_version"] >= 1
        hub.close()

    assert MEMORY_CHAT_LOG_APPEND in events, events
    print("OK memory hub smoke", {"ids": ids, "events": events, "stats_chat_log": st["chat_log"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
