#!/usr/bin/env python3
"""Smoke: MemoryHub SQLite chat_log + people/diary + rag_write_mode gate."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.event_bus import MEMORY_CHAT_LOG_APPEND, EventBus
from core.memory import MemoryHub


class _FakeLTM:
    rag_enabled = True

    def __init__(self) -> None:
        self.saves = 0
        self.knowledge = 0

    def save(self, *a, **k) -> None:
        self.saves += 1

    def add_knowledge(self, text, metadata=None):
        self.knowledge += 1
        return True, "k1"

    def search(self, query, n_results=None):
        return []

    def count(self) -> int:
        return self.knowledge


def main() -> int:
    events: list[str] = []
    bus = EventBus()
    bus.subscribe(MEMORY_CHAT_LOG_APPEND, lambda e: events.append(e.event_type))

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "neyra_memory.db"
        fake = _FakeLTM()
        hub = MemoryHub(
            {"memory": {"sqlite_path": str(db), "rag_write_mode": "important_only"}},
            long_memory=fake,
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
        assert hub.save_dialog_semantic("a", "b", {}) is False
        assert fake.saves == 0
        ok, _ = hub.remember_knowledge("факт", {"type": "knowledge"})
        assert ok and fake.knowledge == 1

        hub.add_person_fact(
            "p1",
            "любит чай",
            emotion_note="тепло",
            aliases=["Алиса"],
            display_name="Алиса",
        )
        hub.add_diary_note("заметка дня", source="smoke", emotion="calm")
        hub.add_journal_entry("итог", title="день", kind="reflection", publish_event=False)
        hub.save_wm_snapshot("# WM\n- task", user_id="u1", publish_event=False)

        snip = hub.working_memory_for_prompt("u1")
        assert "task" in snip or "WM" in snip, snip
        assert "заметка дня" in hub.diary_recent_text(limit=5)

        st = hub.stats()
        assert st["chat_log"] == 2, st
        assert st["people"] == 1, st
        assert st["person_facts"] == 1, st
        assert st["diary_notes"] == 1, st
        assert st["journal_entries"] == 1, st
        assert st["working_memory_snapshots"] == 1, st
        assert st["allows_raw_dialog_embed"] is False

        hub2 = MemoryHub(
            {"memory": {"sqlite_path": str(Path(tmp) / "legacy.db"), "rag_write_mode": "legacy_dialog"}},
            long_memory=fake,
        )
        assert hub2.allows_raw_dialog_embed() is True
        assert hub2.save_dialog_semantic("x", "y", {}) is True
        assert fake.saves == 1
        hub.close()
        hub2.close()

    assert MEMORY_CHAT_LOG_APPEND in events, events
    print("OK memory hub smoke v2", st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
