"""Compat shim — prefer ``from core.runtime import HealthMonitor``."""

from __future__ import annotations

from core.runtime.health import HealthMonitor

__all__ = ["HealthMonitor"]
