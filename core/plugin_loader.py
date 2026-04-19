"""
Minimal plugin loader for interfaces/* plugin.yaml manifests.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

logger = logging.getLogger("neyra.plugins")


@dataclass
class PluginManifest:
    id: str
    name: str
    description: str
    version: str
    enabled: bool
    # resident: load main_script at startup; on_demand: registry only until invoke
    lifecycle: str
    main_script: str
    plugin_dir: Path
    raw: dict[str, Any]


class PluginLoader:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.interfaces_dir = self.root / "interfaces"

    def discover_manifests(self) -> list[PluginManifest]:
        out: list[PluginManifest] = []
        if not self.interfaces_dir.exists():
            return out
        for manifest_path in self.interfaces_dir.glob("*/plugin.yaml"):
            try:
                raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                if not isinstance(raw, dict):
                    continue
                plugin_dir = manifest_path.parent
                lc = str(raw.get("lifecycle") or "resident").strip().lower()
                if lc not in ("resident", "on_demand"):
                    lc = "resident"
                out.append(
                    PluginManifest(
                        id=str(raw.get("id") or plugin_dir.name).strip(),
                        name=str(raw.get("name") or plugin_dir.name).strip(),
                        description=str(raw.get("description") or "").strip(),
                        version=str(raw.get("version") or "0.0.0").strip(),
                        enabled=bool(raw.get("enabled", True)),
                        lifecycle=lc,
                        main_script=str(raw.get("main_script") or "").strip(),
                        plugin_dir=plugin_dir,
                        raw=raw,
                    )
                )
            except Exception as e:
                logger.warning("Bad plugin manifest %s: %s", manifest_path, e)
        return out

    def list_plugins(self) -> list[dict[str, Any]]:
        rows = []
        for p in self.discover_manifests():
            rows.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "version": p.version,
                    "enabled": p.enabled,
                    "lifecycle": p.lifecycle,
                    "main_script": p.main_script,
                    "plugin_dir": str(p.plugin_dir),
                }
            )
        return rows

    def set_enabled(self, plugin_id: str, enabled: bool) -> bool:
        plugin_id = (plugin_id or "").strip().lower()
        if not plugin_id:
            return False
        for manifest_path in self.interfaces_dir.glob("*/plugin.yaml"):
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            if not isinstance(raw, dict):
                continue
            pid = str(raw.get("id") or manifest_path.parent.name).strip().lower()
            if pid != plugin_id:
                continue
            raw["enabled"] = bool(enabled)
            manifest_path.write_text(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            return True
        return False

    def load_enabled_modules(self) -> list[tuple[PluginManifest, ModuleType]]:
        loaded: list[tuple[PluginManifest, ModuleType]] = []
        for p in self.discover_manifests():
            if not p.enabled:
                logger.info("Plugin disabled, skip: %s", p.id)
                continue
            if p.lifecycle == "on_demand":
                logger.info("Plugin on_demand, registry only at startup: %s", p.id)
                continue
            if not p.main_script:
                logger.warning("Plugin %s has empty main_script", p.id)
                continue
            target = (p.plugin_dir / p.main_script).resolve()
            if not target.exists():
                logger.warning("Plugin %s main script not found: %s", p.id, target)
                continue
            mod_name = f"neyra_plugin_{p.id}"
            spec = importlib.util.spec_from_file_location(mod_name, target)
            if spec is None or spec.loader is None:
                logger.warning("Plugin %s spec load failed", p.id)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            loaded.append((p, module))
            logger.info("Plugin loaded: %s (%s)", p.id, p.version)
        return loaded
