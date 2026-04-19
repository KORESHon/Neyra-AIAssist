"""Точка входа плагина local_voice."""

from __future__ import annotations

from core.plugin_sdk import PluginContext


def run_plugin(ctx: PluginContext) -> None:
    from interfaces.local_voice.stub import run_local_voice_agent

    run_local_voice_agent(ctx.config)
