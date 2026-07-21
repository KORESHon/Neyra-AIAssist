"""One-shot import of legacy json/jsonl/md memory into SQLite Hub tables."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("neyra.memory.legacy_import")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def import_people_dir(hub: Any, people_dir: Path) -> dict[str, int]:
    """Import memory/people_db/*.json → people + person_facts."""
    stats = {"people": 0, "facts": 0, "files": 0, "errors": 0}
    if not people_dir.is_dir():
        return stats
    for path in sorted(people_dir.glob("*.json")):
        stats["files"] += 1
        try:
            data = _read_json(path)
            pid = str(data.get("id") or path.stem).strip()
            if not pid:
                stats["errors"] += 1
                continue
            names = list(data.get("names") or [])
            hub.upsert_person(
                pid,
                display_name=(names[0] if names else pid),
                aliases=names,
                meta=data,
            )
            stats["people"] += 1
            for fact_entry in data.get("dynamic_facts") or []:
                if not isinstance(fact_entry, dict):
                    continue
                fact = str(fact_entry.get("fact") or "").strip()
                if not fact:
                    continue
                hub.add_person_fact(
                    pid,
                    fact,
                    emotion_note=str(fact_entry.get("emotion") or "").strip() or None,
                    source="legacy_import",
                    meta=fact_entry,
                    created_at=str(fact_entry.get("date") or "") or None,
                )
                stats["facts"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.warning("legacy_import people %s: %s", path, e)
    return stats


def import_diary_jsonl(hub: Any, diary_path: Path) -> dict[str, int]:
    stats = {"notes": 0, "errors": 0}
    if not diary_path.is_file():
        return stats
    try:
        lines = diary_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        logger.warning("legacy_import diary read: %s", e)
        return {"notes": 0, "errors": 1}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            text = str(entry.get("text") or "").strip()
            if not text:
                continue
            meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
            emo = None
            if isinstance(meta, dict):
                emo = meta.get("emotion") or meta.get("assistant_emotion")
            hub.add_diary_note(
                text,
                source=str(entry.get("source") or "legacy_import"),
                emotion=str(emo)[:500] if emo else None,
                meta=meta or entry,
                ts=str(entry.get("timestamp") or "") or None,
            )
            stats["notes"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.debug("legacy_import diary line: %s", e)
    return stats


def import_journal_json(hub: Any, journal_path: Path) -> dict[str, int]:
    stats = {"entries": 0, "errors": 0}
    if not journal_path.is_file():
        return stats
    try:
        data = _read_json(journal_path)
    except Exception as e:
        logger.warning("legacy_import journal: %s", e)
        return {"entries": 0, "errors": 1}
    rows = data if isinstance(data, list) else [data]
    for item in rows:
        try:
            if isinstance(item, dict):
                text = str(
                    item.get("summary")
                    or item.get("text")
                    or item.get("content")
                    or json.dumps(item, ensure_ascii=False)
                )
                hub.add_journal_entry(
                    text[:20000],
                    title=str(item.get("title") or item.get("date") or "")[:200] or None,
                    kind=str(item.get("kind") or "legacy_import"),
                    meta=item,
                    ts=str(item.get("timestamp") or item.get("date") or "") or None,
                    publish_event=False,
                )
            else:
                hub.add_journal_entry(str(item)[:20000], kind="legacy_import", publish_event=False)
            stats["entries"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.debug("legacy_import journal row: %s", e)
    return stats


def import_working_memory_dir(hub: Any, wm_dir: Path) -> dict[str, int]:
    stats = {"snapshots": 0, "errors": 0}
    if not wm_dir.is_dir():
        return stats
    for path in sorted(wm_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                continue
            user_id = path.stem
            hub.save_wm_snapshot(
                content,
                user_id=user_id,
                meta={"path": str(path), "source": "legacy_import"},
                publish_event=False,
            )
            stats["snapshots"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.warning("legacy_import wm %s: %s", path, e)
    return stats


def _legacy_import_marker_path(hub: Any) -> Path:
    sqlite_path = Path(getattr(getattr(hub, "sqlite", None), "path", None) or "./memory/neyra_memory.db")
    return Path(str(sqlite_path) + ".legacy_import_done")


def run_hub_legacy_import(
    hub: Any,
    config: dict[str, Any],
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Import legacy on-disk stores into SQLite via Hub.
    Paths follow current memory.* config (same as PeopleDB / Diary / journal / WM).

    Idempotent by default: after a successful run a marker file is written next to
    the Hub SQLite DB. Subsequent calls skip unless force=True.
    """
    marker = _legacy_import_marker_path(hub)
    if marker.is_file() and not force:
        logger.info("hub_legacy_import skipped (marker exists): %s", marker)
        return {
            "skipped": True,
            "reason": "already_imported",
            "marker": str(marker),
        }

    mem = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    chroma = Path(str(mem.get("chroma_db_path") or "./memory/chroma_db"))
    base = chroma.parent
    people_dir = base / "people_db"
    diary_path = Path(str(mem.get("diary_path") or "./memory/neyra_diary.jsonl"))
    journal_path = Path(str(mem.get("journal_path") or "./memory/journal.json"))
    wm_dir = Path(str((mem.get("working_memory") or {}).get("storage_dir") or "./memory/working_memory"))

    report: dict[str, Any] = {
        "people": import_people_dir(hub, people_dir),
        "diary": import_diary_jsonl(hub, diary_path),
        "journal": import_journal_json(hub, journal_path),
        "working_memory": import_working_memory_dir(hub, wm_dir),
        "skipped": False,
        "forced": bool(force),
        "marker": str(marker),
    }
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "forced": bool(force),
                    "report": {
                        k: report[k]
                        for k in ("people", "diary", "journal", "working_memory")
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("hub_legacy_import: failed to write marker %s: %s", marker, e)
    logger.info("hub_legacy_import done: %s", report)
    return report
