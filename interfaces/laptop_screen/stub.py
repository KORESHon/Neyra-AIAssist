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
    cfg = ((config.get("plugins") or {}).get("laptop_screen") or {})
    logger.info(
        "laptop_screen_agent пока заглушка | interval=%s s",
        cfg.get("capture_interval_seconds", 2.0),
    )
    logger.info("Реализация будет добавлена отдельным этапом.")

