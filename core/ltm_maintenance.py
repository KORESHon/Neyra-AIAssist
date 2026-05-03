"""
Долговременная память (Chroma): обслуживание и фоновые джобы (этап B3).
Общая логика для Internal API и планировщика.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("neyra.ltm")


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_ltm_archive_dir(config: dict, root: Optional[Path] = None) -> Path:
    root = root or project_root()
    mem_cfg = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    raw_chroma = mem_cfg.get("chroma_db_path", "./memory/chroma_db")
    chroma_path = Path(str(raw_chroma)).expanduser()
    if not chroma_path.is_absolute():
        chroma_path = (root / chroma_path).resolve()
    sub = str(mem_cfg.get("ltm_archive_dir", "ltm_archive")).strip() or "ltm_archive"
    arch = Path(sub).expanduser()
    return arch if arch.is_absolute() else chroma_path.parent / arch


def run_scheduled_prune(agent: Any, config: dict) -> dict[str, Any]:
    """Синхронный prune по расписанию (вызывается из APScheduler)."""
    mem_cfg = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    auto = mem_cfg.get("ltm_auto_prune") if isinstance(mem_cfg.get("ltm_auto_prune"), dict) else {}
    if not bool(auto.get("enabled", False)):
        return {"skipped": True, "reason": "ltm_auto_prune.disabled"}
    older = float(auto.get("older_than_days", 90))
    types = auto.get("types")
    if types is not None and not isinstance(types, list):
        types = None
    dry = bool(auto.get("dry_run", False))
    try:
        res = agent.long_memory.prune_older_than(older, types=types, dry_run=dry)
        logger.info("LTM scheduled prune | %s", res)
        return {"skipped": False, **res}
    except Exception as e:
        logger.exception("LTM scheduled prune failed: %s", e)
        return {"skipped": False, "error": str(e)[:500]}


async def execute_ltm_summarize(
    agent: Any,
    config: dict,
    root: Path,
    *,
    older_than_days: float,
    types: Optional[list[str]],
    dry_run: bool,
    max_entries: int,
    compress_with_llm: bool,
    digest_source: str = "memory_summarize_api",
) -> dict[str, Any]:
    """Полный цикл summarize: опционально digest LLM + cold archive (как POST /v1/memory/summarize)."""

    def _select() -> list[tuple[str, dict[str, Any], str]]:
        rows = agent.long_memory.select_older_than(older_than_days, types=types)
        return rows[:max_entries]

    import asyncio

    rows = await asyncio.to_thread(_select)
    if dry_run:
        return {
            "dry_run": True,
            "would_process": len(rows),
            "digest_would_run": bool(compress_with_llm and rows),
        }

    combined = "\n\n---\n\n".join((r[2] or "") for r in rows)
    digest_id: Optional[str] = None
    digest_chars = 0
    if rows and compress_with_llm:
        digest_text = await agent.summarize_ltm_corpus(combined)
        digest_chars = len(digest_text or "")
        if digest_text:
            meta = {
                "type": "ltm_digest",
                "source": digest_source,
                "covers_older_than_days": str(older_than_days),
            }

            def _add() -> tuple[bool, str]:
                return agent.long_memory.add_knowledge(digest_text, meta)

            ok, info = await asyncio.to_thread(_add)
            if ok:
                digest_id = info

    archive_dir = resolve_ltm_archive_dir(config, root)

    def _arch() -> dict[str, Any]:
        return agent.long_memory.archive_older_than(
            older_than_days,
            archive_dir,
            types=types,
            dry_run=False,
            max_entries=max_entries,
        )

    arch_res = await asyncio.to_thread(_arch)
    return {
        **arch_res,
        "digest_added_id": digest_id,
        "digest_chars": digest_chars,
    }


async def run_scheduled_summarize(agent: Any, config: dict, root: Optional[Path] = None) -> dict[str, Any]:
    """Фоновый summarize по конфигу memory.ltm_auto_summarize."""
    root = root or project_root()
    mem_cfg = config.get("memory") if isinstance(config.get("memory"), dict) else {}
    auto = mem_cfg.get("ltm_auto_summarize") if isinstance(mem_cfg.get("ltm_auto_summarize"), dict) else {}
    if not bool(auto.get("enabled", False)):
        return {"skipped": True, "reason": "ltm_auto_summarize.disabled"}
    try:
        out = await execute_ltm_summarize(
            agent,
            config,
            root,
            older_than_days=float(auto.get("older_than_days", 60)),
            types=auto.get("types") if isinstance(auto.get("types"), list) else None,
            dry_run=bool(auto.get("dry_run", False)),
            max_entries=int(auto.get("max_entries", 500)),
            compress_with_llm=bool(auto.get("compress_with_llm", True)),
            digest_source="ltm_scheduled_summarize",
        )
        logger.info("LTM scheduled summarize | keys=%s", list(out.keys()))
        return {"skipped": False, **out}
    except Exception as e:
        logger.exception("LTM scheduled summarize failed: %s", e)
        return {"skipped": False, "error": str(e)[:500]}
