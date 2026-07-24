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


def _hub_layer_counts(hub: Any) -> dict[str, int]:
    try:
        st = hub.stats() if hasattr(hub, "stats") else {}
    except Exception:
        st = {}
    return {
        "people": int(st.get("people") or 0),
        "diary": int(st.get("diary_notes") or 0),
        "journal": int(st.get("journal_entries") or 0),
        "working_memory": int(st.get("working_memory_snapshots") or 0),
    }


def _legacy_paths(config: dict[str, Any]) -> dict[str, Path]:
    mem = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    chroma = Path(str(mem.get("chroma_db_path") or "./memory/chroma_db"))
    base = chroma.parent
    return {
        "people": base / "people_db",
        "diary": Path(str(mem.get("diary_path") or "./memory/neyra_diary.jsonl")),
        "journal": Path(str(mem.get("journal_path") or "./memory/journal.json")),
        "working_memory": Path(
            str((mem.get("working_memory") or {}).get("storage_dir") or "./memory/working_memory")
        ),
    }


def layers_needing_import(hub: Any, config: dict[str, Any]) -> list[str]:
    """Layers that are empty in Hub but still have on-disk legacy data."""
    counts = _hub_layer_counts(hub)
    paths = _legacy_paths(config)
    need: list[str] = []
    people_dir = paths["people"]
    if counts["people"] == 0 and people_dir.is_dir() and any(people_dir.glob("*.json")):
        need.append("people")
    diary_path = paths["diary"]
    if counts["diary"] == 0 and diary_path.is_file() and diary_path.stat().st_size > 0:
        need.append("diary")
    journal_path = paths["journal"]
    if counts["journal"] == 0 and journal_path.is_file() and journal_path.stat().st_size > 2:
        try:
            data = _read_json(journal_path)
            if (isinstance(data, list) and data) or (isinstance(data, dict) and data):
                need.append("journal")
        except Exception:
            need.append("journal")
    wm_dir = paths["working_memory"]
    if (
        counts["working_memory"] == 0
        and wm_dir.is_dir()
        and any(p.is_file() and p.stat().st_size > 0 for p in wm_dir.glob("*.md"))
    ):
        need.append("working_memory")
    return need


def legacy_files_present(config: dict[str, Any]) -> bool:
    """True if any classic on-disk people/diary/journal/WM store still has data."""
    # Reuse path checks without needing a Hub instance.
    mem = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    chroma = Path(str(mem.get("chroma_db_path") or "./memory/chroma_db"))
    people_dir = chroma.parent / "people_db"
    if people_dir.is_dir() and any(people_dir.glob("*.json")):
        return True
    diary_path = Path(str(mem.get("diary_path") or "./memory/neyra_diary.jsonl"))
    if diary_path.is_file() and diary_path.stat().st_size > 0:
        return True
    journal_path = Path(str(mem.get("journal_path") or "./memory/journal.json"))
    if journal_path.is_file() and journal_path.stat().st_size > 2:
        try:
            data = _read_json(journal_path)
            if isinstance(data, list) and data:
                return True
            if isinstance(data, dict) and data:
                return True
        except Exception:
            return True
    wm_dir = Path(str((mem.get("working_memory") or {}).get("storage_dir") or "./memory/working_memory"))
    if wm_dir.is_dir() and any(p.is_file() and p.stat().st_size > 0 for p in wm_dir.glob("*.md")):
        return True
    return False


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

    Idempotent by default via marker next to the Hub SQLite DB. Marker is ignored when
    Hub still has empty layers that have leftover legacy files (stale marker after DB wipe).
    """
    marker = _legacy_import_marker_path(hub)
    need = layers_needing_import(hub, config)
    counts = _hub_layer_counts(hub)
    hub_struct_empty = all(v == 0 for v in counts.values())

    if marker.is_file() and not force:
        if hub_struct_empty and legacy_files_present(config):
            logger.warning(
                "Ignoring stale legacy_import marker (%s): Hub empty but legacy files present",
                marker,
            )
        elif not need:
            logger.info("hub_legacy_import skipped (marker exists, Hub layers filled): %s", marker)
            return {
                "skipped": True,
                "reason": "already_imported",
                "marker": str(marker),
            }
        else:
            logger.warning(
                "Marker present but Hub missing layers %s with legacy files — importing gaps",
                need,
            )

    if not force and not need and not hub_struct_empty:
        return {
            "skipped": True,
            "reason": "no_gaps",
            "marker": str(marker),
        }

    paths = _legacy_paths(config)
    import_all = force or hub_struct_empty or not need
    layers = ["people", "diary", "journal", "working_memory"] if import_all else list(need)

    report: dict[str, Any] = {
        "people": {"people": 0, "facts": 0, "files": 0, "errors": 0},
        "diary": {"notes": 0, "errors": 0},
        "journal": {"entries": 0, "errors": 0},
        "working_memory": {"snapshots": 0, "errors": 0},
        "skipped": False,
        "forced": bool(force),
        "layers": layers,
        "marker": str(marker),
    }
    if "people" in layers:
        report["people"] = import_people_dir(hub, paths["people"])
    if "diary" in layers:
        report["diary"] = import_diary_jsonl(hub, paths["diary"])
    if "journal" in layers:
        report["journal"] = import_journal_json(hub, paths["journal"])
    if "working_memory" in layers:
        report["working_memory"] = import_working_memory_dir(hub, paths["working_memory"])

    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(
                {
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "forced": bool(force),
                    "layers": layers,
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
