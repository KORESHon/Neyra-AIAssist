"""
Runtime helpers: HTTP server entry, health monitor, Windows patches, secrets.

Canonical imports live here. Flat ``core.server`` / ``core.health_monitor`` /
``core.win_runtime`` / ``core.secrets_loader`` remain as thin compat shims.
"""

from __future__ import annotations

from core.runtime.health import HealthMonitor
from core.runtime.secrets import apply_env_secrets, load_dotenv_file
from core.runtime.server import (
    attach_resident_plugins,
    project_root,
    run_neyra_server,
)
from core.runtime.win_runtime import apply_runtime_patches

__all__ = [
    "HealthMonitor",
    "apply_env_secrets",
    "apply_runtime_patches",
    "attach_resident_plugins",
    "load_dotenv_file",
    "project_root",
    "run_neyra_server",
]
