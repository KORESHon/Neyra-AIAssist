"""Compat shim — prefer ``from core.plugins import PluginContext, run_plugin_entrypoint``."""

from __future__ import annotations

from core.plugins.sdk import PluginContext, run_plugin_entrypoint

__all__ = ["PluginContext", "run_plugin_entrypoint"]
