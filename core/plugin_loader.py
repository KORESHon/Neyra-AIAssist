"""Compat shim — prefer ``from core.plugins import PluginLoader``."""

from __future__ import annotations

from core.plugins.loader import PluginLoader, PluginManifest

__all__ = ["PluginLoader", "PluginManifest"]
