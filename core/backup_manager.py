"""Compat shim — prefer ``from core.runtime.backup import BackupManager``."""

from __future__ import annotations

from core.runtime.backup import BackupManager

__all__ = ["BackupManager"]
