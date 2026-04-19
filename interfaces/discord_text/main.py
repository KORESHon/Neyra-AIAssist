"""Точка входа плагина discord_text."""

from __future__ import annotations

from core.plugin_sdk import PluginContext


def run_plugin(ctx: PluginContext) -> None:
    from interfaces.discord_text.discord_text_bot import run_discord_text_bot

    if ctx.agent is None:
        raise RuntimeError("discord_text requires PluginContext.agent")
    run_discord_text_bot(ctx.agent, ctx.config)
