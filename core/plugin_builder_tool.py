"""Compat shim — prefer ``from core.plugins import create_or_edit_plugin_impl``."""

from __future__ import annotations

from core.plugins.builder import PluginBuilderSettings, create_or_edit_plugin_impl

__all__ = ["PluginBuilderSettings", "create_or_edit_plugin_impl"]
