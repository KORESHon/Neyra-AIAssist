"""
Plugin manager surface for Neyra interfaces/* plugins.

Canonical imports live here. Flat ``core.plugin_*`` modules remain as thin
compat shims for one release.
"""

from __future__ import annotations

from core.plugins.builder import PluginBuilderSettings, create_or_edit_plugin_impl
from core.plugins.config import merge_plugin_configs
from core.plugins.loader import PluginLoader, PluginManifest
from core.plugins.sdk import PluginContext, run_plugin_entrypoint

__all__ = [
    "PluginBuilderSettings",
    "PluginContext",
    "PluginLoader",
    "PluginManifest",
    "create_or_edit_plugin_impl",
    "merge_plugin_configs",
    "run_plugin_entrypoint",
]
