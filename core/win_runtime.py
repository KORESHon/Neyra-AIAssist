"""Compat shim — prefer ``from core.runtime import apply_runtime_patches``."""

from __future__ import annotations

from core.runtime.win_runtime import apply_runtime_patches

__all__ = ["apply_runtime_patches"]
