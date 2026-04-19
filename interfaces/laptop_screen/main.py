"""Точка входа плагина laptop_screen."""

from __future__ import annotations

from core.plugin_sdk import PluginContext


def run_plugin(ctx: PluginContext) -> None:
    from interfaces.laptop_screen.stub import run_laptop_screen_agent

    run_laptop_screen_agent(ctx.config)
