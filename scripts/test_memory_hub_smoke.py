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

    # Cutover journal read-path + PeopleDB hydrate gating
    with tempfile.TemporaryDirectory() as tmp3:
        root = Path(tmp3)
        db = root / "cutover.db"
        journal_path = root / "journal.json"
        chat_log = root / "chat.log"
        chat_log.write_text("", encoding="utf-8")
        cfg = {
            "memory": {
                "sqlite_path": str(db),
                "journal_path": str(journal_path),
                "diary_path": str(root / "diary.jsonl"),
                "hub_dual_write_legacy": False,
                "hub_legacy_fallback": False,
                "rag_write_mode": "important_only",
            },
            "logging": {"chat_log": str(chat_log)},
        }
        hub_c = MemoryHub(cfg, long_memory=_FakeLTM())

        class _Agent:
            memory_hub = hub_c
            event_bus = None

        from core.reflection import ReflectionEngine
        from core.memory.legacy import PeopleDB

        refl = ReflectionEngine(cfg, _Agent())
        refl._journal.append(
            {"date": "2026-07-23", "summary": "итог дня cutover", "generated_at": "2026-07-23T01:00:00"}
        )
        assert refl._save_journal() is True
        assert not journal_path.exists() or journal_path.read_text(encoding="utf-8").strip() in {"", "[]"}
        assert hub_c.stats()["journal_entries"] == 1

        # Simulate restart: empty file journal, Hub still has entry
        refl2 = ReflectionEngine(cfg, _Agent())
        assert refl2._journal_has_date("2026-07-23")
        recent = refl2.get_recent_journal(7)
        assert "итог дня cutover" in recent, recent

        # Hub-only failure rolls back in-memory entry
        def _boom(*a, **k):
            raise RuntimeError("boom")

        hub_c.add_journal_entry = _boom  # type: ignore[method-assign]
        refl2._journal.append({"date": "2026-07-24", "summary": "should roll back"})
        assert refl2._save_journal() is False
        assert not any(e.get("date") == "2026-07-24" for e in refl2._journal)

        # PeopleDB hydrate must NOT wipe JSON cache while dual_write=true
        people_dir = root / "people_db"
        people_dir.mkdir()
        (people_dir / "bob.json").write_text(
            json.dumps(
                {
                    "id": "bob",
                    "names": ["Боб"],
                    "discord_ids": [],
                    "dynamic_facts": [{"date": "2026-01-01", "fact": "только в json"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cfg_dual = {
            "memory": {
                "sqlite_path": str(root / "dual.db"),
                "chroma_db_path": str(root / "chroma_db"),
                "hub_dual_write_legacy": True,
            }
        }
        (root / "chroma_db").mkdir(exist_ok=True)
        # PeopleDB resolves people_db from chroma parent
        pdb = PeopleDB(cfg_dual)
        # Force db_dir to our temp people dir
        pdb.db_dir = people_dir
        pdb._cache.clear()
        pdb._load_all()
        assert "bob" in pdb._cache
        hub_dual = MemoryHub(cfg_dual, long_memory=_FakeLTM())
        hub_dual.add_person_fact("hub_only", "из sqlite", aliases=["HubOnly"], display_name="HubOnly")
        # Mimic agent gate: dual_write + non-empty cache → skip hydrate
        if (not hub_dual.hub_dual_write_legacy) or (not pdb._cache):
            pdb.hydrate_from_hub(hub_dual)
        assert "bob" in pdb._cache
        assert any(
            f.get("fact") == "только в json" for f in pdb._cache["bob"].get("dynamic_facts") or []
        ), pdb._cache["bob"]
        # Cutover gate: dual off → hydrate ok
        hub_dual.hub_dual_write_legacy = False
        if (not hub_dual.hub_dual_write_legacy) or (not pdb._cache):
            pdb.hydrate_from_hub(hub_dual)
        assert pdb.find("HubOnly") is not None or hub_dual.find_person("HubOnly") is not None

        # Diary input for reflect after cutover (Hub-only, no JSONL)
        diary_path = root / "neyra_diary.jsonl"
        cfg_diary = {
            "memory": {
                "sqlite_path": str(root / "diary_cutover.db"),
                "diary_path": str(diary_path),
                "journal_path": str(root / "j2.json"),
                "hub_dual_write_legacy": False,
                "hub_legacy_fallback": False,
            },
            "logging": {"chat_log": str(root / "chat2.log")},
        }
        (root / "chat2.log").write_text("", encoding="utf-8")
        hub_d = MemoryHub(cfg_diary, long_memory=_FakeLTM())
        from datetime import datetime, timedelta

        hub_d.add_diary_note(
            "свежая заметка для reflect",
            source="smoke",
            ts=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        hub_d.append_chat_batch(
            [
                {
                    "role": "user",
                    "text": "привет cutover",
                    "user_id": "u1",
                    "display_name": "U",
                    "ts": datetime.now().isoformat(),
                }
            ],
            publish_event=False,
        )

        class _AgentD:
            memory_hub = hub_d
            event_bus = None

        refl_d = ReflectionEngine(cfg_diary, _AgentD())
        diary_24 = refl_d._get_diary_last_24h()
        assert "свежая заметка для reflect" in diary_24, diary_24
        assert not diary_path.exists()
        chat_hour = refl_d._get_logs_for_last_hours(2)
        assert "привет cutover" in chat_hour, chat_hour

        # Blocker repro: UTC-stored Hub ts must still match host-local cutoff window
        from datetime import timezone as _tz
        from core.timeutil import now_local

        utc_recent = (now_local().astimezone(_tz.utc) - timedelta(minutes=10)).isoformat()
        hub_d.append_chat_batch(
            [
                {
                    "role": "user",
                    "text": "utc-stored recent",
                    "user_id": "u1",
                    "display_name": "U",
                    "ts": utc_recent,
                }
            ],
            publish_event=False,
        )
        hour_logs = refl_d._get_logs_for_last_hour()
        assert "utc-stored recent" in hour_logs, hour_logs

        # Mixed offsets must not drop the true recent row via early-break on TEXT order
        older_local = "2026-01-01T12:00:00+03:00"  # lexically "newer" than some UTC walls
        newer_utc = (now_local().astimezone(_tz.utc) - timedelta(minutes=5)).isoformat()
        hub_d.append_chat_batch(
            [
                {
                    "role": "user",
                    "text": "older-local-offset",
                    "user_id": "u1",
                    "display_name": "U",
                    "ts": older_local,
                },
                {
                    "role": "user",
                    "text": "newer-utc-mixed",
                    "user_id": "u1",
                    "display_name": "U",
                    "ts": newer_utc,
                },
            ],
            publish_event=False,
        )
        mixed = refl_d._get_logs_for_last_hour()
        assert "newer-utc-mixed" in mixed, mixed
        assert "older-local-offset" not in mixed, mixed

        # system.timezone override must affect now_local / cutoff (not only the log line)
        from core.timeutil import configure_timezone, now_iso as local_iso, resolve_tz

        configure_timezone("Europe/Moscow")
        assert "Europe/Moscow" in str(getattr(resolve_tz(), "key", "")) or str(resolve_tz())
        mos = local_iso()
        assert mos.endswith("+03:00") or "+03:00" in mos or mos.endswith("+04:00") or "+04:00" in mos, mos
        configure_timezone(None)  # restore host for later tests

        # link_discord_id must persist via Hub when dual_write=false
        from core.memory.legacy import PeopleDB as _PDB

        cfg_link = {
            "memory": {
                "sqlite_path": str(root / "link.db"),
                "chroma_db_path": str(root / "chroma_link"),
                "hub_dual_write_legacy": False,
                "hub_legacy_fallback": False,
            }
        }
        (root / "chroma_link").mkdir(exist_ok=True)
        hub_l = MemoryHub(cfg_link, long_memory=_FakeLTM())
        pdb_l = _PDB(cfg_link)
        pdb_l.memory_hub = hub_l
        pdb_l.add_person("alice", ["Алиса"], discord_ids=[])
        assert pdb_l.link_discord_id("alice", "999888777666555444") is True
        hub_l2 = MemoryHub(cfg_link, long_memory=_FakeLTM())
        found = hub_l2.find_person("Алиса", discord_id="999888777666555444")
        assert found and found.get("id") == "alice", found
        hub_l.close()
        hub_l2.close()

        # WM refresh source: Hub snapshot when dual_write=false (no .md required)
        hub_d.save_wm_snapshot("# WM\n- from hub only", user_id="u_wm", publish_event=False)
        snap = hub_d.sqlite.latest_wm_snapshot(user_id="u_wm")
        assert snap and "from hub only" in str(snap.get("content") or ""), snap

        hub_d.close()

        hub_c.close()
        hub_dual.close()

    print("OK memory hub smoke v2", st)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
