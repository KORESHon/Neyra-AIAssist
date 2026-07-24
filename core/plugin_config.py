"""Compat shim — prefer ``from core.plugins import merge_plugin_configs``."""

from __future__ import annotations

from core.plugins.config import merge_plugin_configs

__all__ = ["merge_plugin_configs"]
