"""
Example plugin entrypoint.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("neyra.plugin.example")


def setup(context: dict[str, Any] | None = None) -> None:
    logger.info("Example plugin setup | context_keys=%s", list((context or {}).keys()))


def handle_event(event: Any) -> None:
    logger.debug("Example plugin got event: %s", event)


def shutdown() -> None:
    logger.info("Example plugin shutdown")
