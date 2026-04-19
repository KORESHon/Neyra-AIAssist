"""
Laptop screen agent stub (future plugin).

Цель:
- периодический скриншот экрана,
- передача изображения в vision-часть ядра,
- подготовка контекста для LLM.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("neyra.screen_agent")


def run_laptop_screen_agent(config: dict) -> None:
    cfg = ((config.get("interfaces") or {}).get("laptop_screen_agent") or {})
    logger.info(
        "laptop_screen_agent пока заглушка | interval=%s | enabled=%s",
        cfg.get("capture_interval_seconds", 2.0),
        bool(cfg.get("enabled", False)),
    )
    logger.info("Реализация будет добавлена отдельным этапом.")

