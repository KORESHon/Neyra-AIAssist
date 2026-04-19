"""
Local voice agent stub (future plugin).

Цель:
- wake-word на локальном микрофоне,
- запись реплики до тишины,
- STT -> LLM -> TTS,
- вывод в наушники и (опционально) VB-Cable.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("neyra.local_voice")


def run_local_voice_agent(config: dict) -> None:
    cfg = ((config.get("interfaces") or {}).get("local_voice_agent") or {})
    logger.info(
        "local_voice_agent пока заглушка | wake_word=%s | enabled=%s",
        cfg.get("wake_word", "нейра"),
        bool(cfg.get("enabled", False)),
    )
    logger.info("Реализация будет добавлена отдельным этапом.")

