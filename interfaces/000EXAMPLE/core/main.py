"""
Точка входа плагина 000EXAMPLE.

Обязательный контракт Neyra Plugin SDK: экспорт функции run_plugin(ctx).
См. HELP.md, HELP-RU.md и help.html в каталоге плагина.
"""

from __future__ import annotations

import logging
from typing import Any

from core.plugin_sdk import PluginContext

logger = logging.getLogger("neyra.plugin.example")


def run_plugin(ctx: PluginContext) -> None:
    """
    Синхронная точка входа. Вызывается из main.py при запуске режима из cli_modes
    или при явной загрузке плагина. Блокирующий код допустим (как discord.run / uvicorn.run).
    """
    logger.info(
        "000EXAMPLE run_plugin | root=%s | agent=%s",
        ctx.root,
        "yes" if ctx.agent is not None else "no",
    )
    # Учебный плагин: не поднимает сеть и не требует секретов.
    print(
        "[000EXAMPLE] Плагин отработал. Для реального интерфейса см. interfaces/discord_text/ "
        "или interfaces/internal_api/."
    )


# Необязательные заготовки под будущий SDK (события / горячая перезагрузка):
def setup(context: dict[str, Any] | None = None) -> None:
    logger.info("Example plugin setup | context_keys=%s", list((context or {}).keys()))


def handle_event(event: Any) -> None:
    logger.debug("Example plugin got event: %s", event)


def shutdown() -> None:
    logger.info("Example plugin shutdown")
