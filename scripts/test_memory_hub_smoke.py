#!/usr/bin/env python3
"""Smoke: MemoryHub SQLite chat_log + people/diary + rag_write_mode gate."""

from __future__ import annotations

import json
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
            person_meta={"discord_ids": ["123456789012345678"], "names": ["Алиса"]},
        )
        hub.add_diary_note("заметка дня", source="smoke", emotion="calm")
        hub.add_journal_entry("итог", title="день", kind="reflection", publish_event=False)
        hub.save_wm_snapshot("# WM\n- task", user_id="u1", publish_event=False)

        # Cutover-safe identity: SQLite lookup without legacy PeopleDB cache
        found = hub.find_person("Алиса")
        assert found and found.get("id") == "p1", found
        assert hub.find_person("nobody") is None
        assert hub.get_all_names_map().get("алиса") == "p1"
        assert "любит чай" in hub.get_person_summary("p1")

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

        # Restart simulation: new Hub on same DB still finds the person
        hub_re = MemoryHub(
            {"memory": {"sqlite_path": str(db), "rag_write_mode": "important_only", "hub_legacy_fallback": False}},
            long_memory=fake,
            event_bus=bus,
        )
        assert hub_re.find_person("Алиса", discord_id="123456789012345678")
        hub_re.close()

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

    # legacy import smoke
    with tempfile.TemporaryDirectory() as tmp2:
        root = Path(tmp2)
        people = root / "people_db"
        people.mkdir()
        (people / "alice.json").write_text(
            json.dumps(
                {
                    "id": "alice",
                    "names": ["Алиса"],
                    "discord_ids": ["123456789012345678"],
                    "dynamic_facts": [{"date": "2026-01-01", "fact": "любит чай"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        diary = root / "neyra_diary.jsonl"
        diary.write_text(
            json.dumps({"timestamp": "2026-01-01T00:00:00", "source": "t", "text": "из jsonl"}, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        cfg = {
            "memory": {
                "sqlite_path": str(root / "import.db"),
                "chroma_db_path": str(root / "chroma_db"),
                "diary_path": str(diary),
                "journal_path": str(root / "missing_journal.json"),
                "working_memory": {"storage_dir": str(root / "wm")},
                "hub_legacy_fallback": False,
                "hub_dual_write_legacy": False,
            }
        }
        (root / "chroma_db").mkdir()
        hub_i = MemoryHub(cfg)
        from core.memory.legacy_import import run_hub_legacy_import

        rep = run_hub_legacy_import(hub_i, cfg)
        assert rep["people"]["people"] == 1, rep
        assert rep["people"]["facts"] == 1, rep
        assert rep["diary"]["notes"] == 1, rep
        assert hub_i.stats()["person_facts"] >= 1
        assert "из jsonl" in hub_i.diary_recent_text(5)
        hub_i.close()

    print("OK memory hub smoke v2", st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
