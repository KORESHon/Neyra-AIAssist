#!/usr/bin/env python3
"""Offline cutover acceptance for Memory Hub Phase 1A (no live Discord/API server).

Simulates: dual-write on → data in SQLite → flags off → restart Hub → all reads still work
without JSON/JSONL/MD primary files.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.memory import MemoryHub
from core.memory.legacy import NeyraDiary, PeopleDB
from core.reflection import ReflectionEngine
from core.timeutil import now_local


class _FakeLTM:
    rag_enabled = True

    def save(self, *a, **k) -> None:
        return None

    def add_knowledge(self, text, metadata=None):
        return True, "k1"

    def search(self, query, n_results=None):
        return []

    def count(self) -> int:
        return 0


def _cfg(root: Path, *, dual: bool, fallback: bool) -> dict:
    return {
        "memory": {
            "sqlite_path": str(root / "neyra_memory.db"),
            "chroma_db_path": str(root / "chroma_db"),
            "diary_path": str(root / "neyra_diary.jsonl"),
            "journal_path": str(root / "journal.json"),
            "hub_dual_write_legacy": dual,
            "hub_legacy_fallback": fallback,
            "hub_legacy_import": False,
            "rag_write_mode": "important_only",
            "working_memory": {
                "enabled": True,
                "storage_dir": str(root / "working_memory"),
            },
        },
        "logging": {"chat_log": str(root / "chat.log")},
        "system": {"timezone": None},
    }


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "chroma_db").mkdir()
        (root / "chat.log").write_text("", encoding="utf-8")

        # --- Phase A: dual-write ON (migration contour) ---
        cfg_a = _cfg(root, dual=True, fallback=True)
        hub_a = MemoryHub(cfg_a, long_memory=_FakeLTM())
        people = PeopleDB(cfg_a)
        people.memory_hub = hub_a
        diary = NeyraDiary(cfg_a)
        diary.memory_hub = hub_a

        created = people.add_person(
            "cutover_user",
            ["Катя", "Kate"],
            discord_ids=["123456789012345678"],
        )
        assert created.get("id") == "cutover_user"
        assert people.update_fact("cutover_user", "любит чай", emotion="тепло") is True
        assert people.link_discord_id("cutover_user", "123456789012345678") is False  # already linked
        assert diary.add_entry("заметка dual", source="cutover") is True
        hub_a.add_journal_entry(
            "рефлексия dual",
            title="2026-07-23",
            kind="reflection",
            meta={"date": "2026-07-23", "summary": "рефлексия dual"},
            publish_event=False,
        )
        hub_a.save_wm_snapshot("# WM\n- task dual", user_id="u_cut", publish_event=False)
        hub_a.append_chat_batch(
            [
                {
                    "role": "user",
                    "text": "привет cutover",
                    "user_id": "u_cut",
                    "display_name": "Катя",
                    "channel_id": "c1",
                    "ts": now_local().isoformat(),
                },
                {
                    "role": "assistant",
                    "text": "хай",
                    "user_id": "u_cut",
                    "display_name": "Нейра",
                    "channel_id": "c1",
                    "ts": now_local().isoformat(),
                },
            ],
            publish_event=False,
        )
        st_a = hub_a.stats()
        assert st_a["people"] >= 1 and st_a["person_facts"] >= 1
        assert st_a["diary_notes"] >= 1 and st_a["journal_entries"] >= 1
        assert st_a["working_memory_snapshots"] >= 1 and st_a["chat_log"] >= 2
        hub_a.close()

        # Remove legacy files to prove Hub is enough after cutover
        for p in [
            root / "neyra_diary.jsonl",
            root / "journal.json",
        ]:
            if p.exists():
                p.unlink()
        pdb_dir = people.db_dir
        if pdb_dir.is_dir():
            for jf in pdb_dir.glob("*.json"):
                jf.unlink()
        wm_dir = root / "working_memory"
        if wm_dir.is_dir():
            for f in wm_dir.glob("*.md"):
                f.unlink()

        # --- Phase B: dual_write OFF + fallback OFF (cutover) ---
        cfg_b = _cfg(root, dual=False, fallback=False)
        hub_b = MemoryHub(cfg_b, long_memory=_FakeLTM())
        people_b = PeopleDB(cfg_b)
        people_b.memory_hub = hub_b
        people_b.hydrate_from_hub(hub_b)
        diary_b = NeyraDiary(cfg_b)
        diary_b.memory_hub = hub_b

        class _Agent:
            memory_hub = hub_b
            event_bus = None
            people_db = people_b
            diary = diary_b

        refl = ReflectionEngine(cfg_b, _Agent())

        # Identity + summary survive without JSON
        found = hub_b.find_person("Катя", discord_id="123456789012345678")
        assert found and found.get("id") == "cutover_user", found
        summary = hub_b.get_person_summary("cutover_user")
        assert "любит чай" in summary, summary
        assert hub_b.get_all_names_map().get("катя") == "cutover_user"

        # Diary / journal / chat / WM reads
        assert "заметка dual" in hub_b.diary_recent_text(10)
        assert "заметка dual" in refl._get_diary_last_24h()
        assert hub_b.list_journal_entries(limit=5)
        assert "привет cutover" in refl._get_logs_for_last_hours(24)
        assert "task dual" in hub_b.working_memory_for_prompt("u_cut")

        # Hub-only writes still work
        assert diary_b.add_entry("после cutover", source="cutover") is True
        assert not (root / "neyra_diary.jsonl").exists()
        assert people_b.update_fact("cutover_user", "факт после cutover") is True
        assert "факт после cutover" in hub_b.get_person_summary("cutover_user")

        # Seed must NOT wipe Hub people when JSON dir empty under dual=false
        # (agent._init_people_db logic mirrored)
        if int(hub_b.stats().get("people") or 0) > 0 or people_b._cache:
            pass  # skip seed — required cutover invariant
        else:
            raise AssertionError("Hub people missing after cutover restart")

        hub_b.close()

    print("OK memory cutover offline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
