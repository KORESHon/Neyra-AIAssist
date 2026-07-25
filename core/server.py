"""Compat shim — prefer ``from core.runtime import run_neyra_server``."""

from __future__ import annotations

from core.runtime.server import attach_resident_plugins, project_root, run_neyra_server

__all__ = ["attach_resident_plugins", "project_root", "run_neyra_server"]
