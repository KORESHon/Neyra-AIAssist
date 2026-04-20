"""
Internal API (v1): маршруты FastAPI и сборка приложения (`build_app`).

Процесс поднимается из ядра — `core.server.run_neyra_server`; папка `interfaces/internal_api/`
остаётся модулем маршрутов и точкой `main_script` для PluginLoader.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from fastapi import Depends, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.agent import NeyraAgent
from core.backup_manager import BackupManager
from core.event_bus import CoreEvent
from core.health_monitor import HealthMonitor
from core.plugin_loader import PluginLoader
from core.plugin_sdk import PluginContext, run_plugin_entrypoint
from core.reflection import ReflectionEngine

logger = logging.getLogger("neyra.api")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dashboard_dist_path(config: dict) -> Path:
    dash = config.get("dashboard") or {}
    raw = str(dash.get("dist_path") or "frontend/dist").strip()
    p = Path(raw)
    if not p.is_absolute():
        p = (_project_root() / p).resolve()
    return p


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _trace_id(request: Request) -> str:
    return str(request.headers.get("x-trace-id") or uuid.uuid4())


def _err_payload(trace_id: str, code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}, "trace_id": trace_id}


def _api_token(cfg: dict) -> str:
    api_cfg = cfg.get("internal_api") or {}
    return str(api_cfg.get("token") or "").strip()


def _require_auth(authorization: Optional[str], cfg: dict) -> None:
    token = _api_token(cfg)
    if not token:
        return
    raw = (authorization or "").strip()
    if not raw.startswith("Bearer "):
        raise ApiError("unauthorized", "Missing bearer token", 401)
    got = raw.removeprefix("Bearer ").strip()
    if got != token:
        raise ApiError("unauthorized", "Invalid bearer token", 401)


def _require_ws_auth(token_qs: Optional[str], authorization: Optional[str], cfg: dict) -> None:
    token = _api_token(cfg)
    if not token:
        return
    # Allow either ?token=... or Authorization: Bearer ...
    if token_qs and token_qs.strip() == token:
        return
    _require_auth(authorization, cfg)


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=6000)
    username: Optional[str] = Field(default=None, max_length=120)
    platform_user_id: Optional[str] = Field(default=None, max_length=120)
    channel_id: Optional[str] = Field(default=None, max_length=120)


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1200)
    top_k: int = Field(default=3, ge=1, le=20)


class MemoryWriteRequest(BaseModel):
    user_text: str = Field(min_length=1, max_length=6000)
    assistant_text: str = Field(min_length=1, max_length=6000)
    username: Optional[str] = Field(default=None, max_length=120)
    platform_user_id: Optional[str] = Field(default=None, max_length=120)


class NotifyRequest(BaseModel):
    event_type: str = Field(min_length=3, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="api.notify", max_length=120)


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)


class PluginStateUpdateRequest(BaseModel):
    enabled: bool


class PluginConfigUpdateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class PluginInvokeRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookRouteCreateRequest(BaseModel):
    route_id: Optional[str] = Field(default=None, max_length=120)
    event_type: str = Field(min_length=1, max_length=120)
    target_url: str = Field(min_length=8, max_length=2048)
    secret: str = Field(default="", max_length=512)
    enabled: bool = True
    max_retries: int = Field(default=3, ge=0, le=10)


class WebhookRouteUpdateRequest(BaseModel):
    event_type: Optional[str] = Field(default=None, min_length=1, max_length=120)
    target_url: Optional[str] = Field(default=None, min_length=8, max_length=2048)
    secret: Optional[str] = Field(default=None, max_length=512)
    enabled: Optional[bool] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)


class WebhookTestRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class WebhookRetryRequest(BaseModel):
    delay_seconds: float = Field(default=0.0, ge=0.0, le=300.0)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mask_secret(s: str) -> str:
    raw = (s or "").strip()
    if not raw:
        return ""
    if len(raw) <= 6:
        return "*" * len(raw)
    return f"{raw[:3]}...{raw[-3:]}"


class WebhookStore:
    def __init__(self, root: Path):
        self.path = root / "logs" / "webhooks_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"routes": {}, "deliveries": {}, "dlq": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {"routes": {}, "deliveries": {}, "dlq": {}}
            raw.setdefault("routes", {})
            raw.setdefault("deliveries", {})
            raw.setdefault("dlq", {})
            return raw
        except Exception:
            return {"routes": {}, "deliveries": {}, "dlq": {}}

    async def _save(self) -> None:
        text = json.dumps(self._state, ensure_ascii=False, indent=2)
        self.path.write_text(text, encoding="utf-8")

    async def list_routes(self) -> list[dict[str, Any]]:
        async with self._lock:
            out: list[dict[str, Any]] = []
            for row in self._state["routes"].values():
                x = dict(row)
                x["secret_masked"] = _mask_secret(str(x.get("secret") or ""))
                x.pop("secret", None)
                out.append(x)
            out.sort(key=lambda r: str(r.get("route_id") or ""))
            return out

    async def get_route(self, route_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = self._state["routes"].get(route_id)
            if not isinstance(row, dict):
                return None
            out = dict(row)
            out["secret_masked"] = _mask_secret(str(out.get("secret") or ""))
            out.pop("secret", None)
            return out

    async def upsert_route(self, route: dict[str, Any]) -> dict[str, Any]:
        rid = str(route.get("route_id") or "").strip()
        if not rid:
            rid = f"route_{uuid.uuid4().hex[:10]}"
        async with self._lock:
            base = self._state["routes"].get(rid) or {}
            merged = {
                **base,
                **route,
                "route_id": rid,
                "updated_at": _utc_now(),
            }
            if "created_at" not in merged:
                merged["created_at"] = _utc_now()
            self._state["routes"][rid] = merged
            await self._save()
            out = dict(merged)
            out["secret_masked"] = _mask_secret(str(out.get("secret") or ""))
            out.pop("secret", None)
            return out

    async def delete_route(self, route_id: str) -> bool:
        async with self._lock:
            if route_id not in self._state["routes"]:
                return False
            self._state["routes"].pop(route_id, None)
            await self._save()
            return True

    async def add_delivery(self, row: dict[str, Any]) -> dict[str, Any]:
        did = f"delivery_{uuid.uuid4().hex}"
        payload = {
            "delivery_id": did,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
            **row,
        }
        async with self._lock:
            self._state["deliveries"][did] = payload
            if payload.get("status") == "failed":
                self._state["dlq"][did] = payload
            await self._save()
        return payload

    async def update_delivery(self, delivery_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        async with self._lock:
            row = self._state["deliveries"].get(delivery_id)
            if not isinstance(row, dict):
                return None
            row.update(updates)
            row["updated_at"] = _utc_now()
            self._state["deliveries"][delivery_id] = row
            if row.get("status") == "failed":
                self._state["dlq"][delivery_id] = row
            else:
                self._state["dlq"].pop(delivery_id, None)
            await self._save()
            return dict(row)

    async def list_deliveries(self, status: str = "") -> list[dict[str, Any]]:
        async with self._lock:
            rows = list(self._state["deliveries"].values())
            if status:
                rows = [r for r in rows if str(r.get("status") or "") == status]
            rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
            return [dict(r) for r in rows]

    async def list_dlq(self) -> list[dict[str, Any]]:
        async with self._lock:
            rows = list(self._state["dlq"].values())
            rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
            return [dict(r) for r in rows]

    async def get_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        async with self._lock:
            row = self._state["deliveries"].get(delivery_id)
            return dict(row) if isinstance(row, dict) else None


async def _dispatch_webhook(
    store: WebhookStore,
    route: dict[str, Any],
    payload: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    max_retries = max(0, int(route.get("max_retries", 3)))
    target_url = str(route.get("target_url") or "").strip()
    if not target_url:
        return await store.add_delivery(
            {
                "route_id": route.get("route_id"),
                "event_type": route.get("event_type"),
                "source": source,
                "status": "failed",
                "attempts": 0,
                "error": "target_url is empty",
                "payload": payload,
            }
        )
    delivery = await store.add_delivery(
        {
            "route_id": route.get("route_id"),
            "event_type": route.get("event_type"),
            "source": source,
            "status": "pending",
            "attempts": 0,
            "payload": payload,
            "target_url": target_url,
        }
    )
    delivery_id = str(delivery.get("delivery_id") or "")
    secret = str(route.get("secret") or "")
    for attempt in range(max_retries + 1):
        headers = {"Content-Type": "application/json"}
        if secret:
            headers["x-neyra-webhook-secret"] = secret
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(target_url, json=payload, headers=headers)
            ok = 200 <= resp.status_code < 300
            status = "ok" if ok else "failed"
            await store.update_delivery(
                delivery_id,
                {
                    "attempts": attempt + 1,
                    "status_code": resp.status_code,
                    "status": status,
                    "response_text": (resp.text or "")[:2000],
                    "error": "" if ok else f"HTTP {resp.status_code}",
                },
            )
            if ok:
                row = await store.get_delivery(delivery_id)
                return row or {}
        except Exception as ex:
            await store.update_delivery(
                delivery_id,
                {
                    "attempts": attempt + 1,
                    "status": "failed",
                    "error": str(ex)[:800],
                },
            )
        if attempt < max_retries:
            await asyncio.sleep(0.5 * (attempt + 1))
    row = await store.get_delivery(delivery_id)
    return row or {}


def build_app(
    config: dict,
    *,
    shared_agent: Optional[NeyraAgent] = None,
    shared_monitor: Optional[HealthMonitor] = None,
    shared_backup_manager: Optional[BackupManager] = None,
    reflection: Optional[ReflectionEngine] = None,
) -> FastAPI:
    app = FastAPI(title="Neyra Internal API", version="1.0")
    if shared_agent is not None:
        agent = shared_agent
        if shared_monitor is None or shared_backup_manager is None:
            raise ValueError("shared_monitor and shared_backup_manager are required with shared_agent")
        monitor = shared_monitor
        backup_manager = shared_backup_manager
    else:
        agent = NeyraAgent(config)
        monitor = HealthMonitor(config, project_root=_project_root())
        backup_manager = BackupManager(config)
    app.state.agent = agent
    app.state.monitor = monitor
    app.state.backup_manager = backup_manager
    app.state.config = config
    ws_cfg = (config.get("internal_api") or {}).get("websocket") or {}
    ws_idle_timeout = max(5, int(ws_cfg.get("idle_timeout_seconds", 60)))
    ws_ping_interval = max(2, int(ws_cfg.get("ping_interval_seconds", 20)))
    ws_close_grace = max(1, int(ws_cfg.get("close_grace_seconds", 5)))
    root = _project_root()
    webhook_store = WebhookStore(root)
    plugin_ops: dict[str, dict[str, Any]] = {}

    @app.on_event("startup")
    async def _startup() -> None:
        if reflection is not None:
            reflection.start_scheduler()
        monitor.start()
        await monitor.run_once()

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError):
        trace_id = _trace_id(request)
        return JSONResponse(
            status_code=exc.status_code,
            content=_err_payload(trace_id, exc.code, exc.message),
            headers={"x-trace-id": trace_id},
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception):
        trace_id = _trace_id(request)
        logger.exception("Unhandled API error | trace_id=%s", trace_id)
        return JSONResponse(
            status_code=500,
            content=_err_payload(trace_id, "internal_error", str(exc)[:500]),
            headers={"x-trace-id": trace_id},
        )

    async def _auth_dep(authorization: Optional[str] = Header(default=None)):
        _require_auth(authorization, config)

    @app.post("/v1/chat")
    async def v1_chat(body: ChatRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        out = await agent.chat(
            user_message=body.text,
            username=body.username or "api_user",
            discord_user_id=body.platform_user_id,
            channel_id=body.channel_id,
        )
        return {"ok": True, "trace_id": trace_id, "data": out}

    @app.post("/v1/memory/search")
    async def v1_memory_search(body: MemorySearchRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        rows = agent.long_memory.search(body.query, n_results=body.top_k)
        return {"ok": True, "trace_id": trace_id, "data": {"results": rows}}

    @app.post("/v1/memory/write")
    async def v1_memory_write(body: MemoryWriteRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        uid = agent.identity.resolve("api", body.platform_user_id or body.username or "unknown")
        meta = {
            "username": body.username or "api_user",
            "discord_id": body.platform_user_id or "",
            "user_id": uid,
            "source": "internal_api",
        }
        agent.long_memory.save(body.user_text, body.assistant_text, meta)
        return {"ok": True, "trace_id": trace_id, "data": {"written": True, "user_id": uid}}

    @app.post("/v1/notify")
    async def v1_notify(body: NotifyRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        agent.event_bus.publish(
            CoreEvent(
                body.event_type,
                body.source,
                body.payload,
            )
        )
        routes = await webhook_store.list_routes()
        for route in routes:
            if not bool(route.get("enabled", True)):
                continue
            if str(route.get("event_type") or "") != body.event_type:
                continue
            asyncio.create_task(
                _dispatch_webhook(
                    webhook_store,
                    route,
                    {
                        "event_type": body.event_type,
                        "source": body.source,
                        "payload": body.payload,
                        "ts": _utc_now(),
                    },
                    source="event_bus",
                )
            )
        return {"ok": True, "trace_id": trace_id, "data": {"published": True}}

    @app.get("/v1/health")
    async def v1_health(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        rep = await monitor.run_once()
        return {"ok": True, "trace_id": trace_id, "data": rep}

    @app.get("/v1/memory/stats")
    async def v1_memory_stats(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        return {
            "ok": True,
            "trace_id": trace_id,
            "data": {
                "short_memory_size": len(agent.short_memory),
                "long_memory_records": agent.long_memory.count(),
                "people_records": len(agent.people_db._cache),
            },
        }

    @app.get("/v1/plugins")
    async def v1_plugins(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(_project_root())
        return {"ok": True, "trace_id": trace_id, "data": {"plugins": loader.list_plugins()}}

    def _find_manifest(loader: PluginLoader, plugin_id: str):
        pid = (plugin_id or "").strip().lower()
        for m in loader.discover_manifests():
            if m.id.strip().lower() == pid:
                return m
        return None

    def _plugin_config_path(manifest) -> Path:
        return manifest.plugin_dir / "config.yaml"

    @app.get("/v1/plugins/{plugin_id}")
    async def v1_plugin_get(plugin_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        cfg_path = _plugin_config_path(m)
        cfg: dict[str, Any] = {}
        if cfg_path.is_file():
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                cfg = raw
        return {
            "ok": True,
            "trace_id": trace_id,
            "data": {
                "plugin": {
                    "id": m.id,
                    "name": m.name,
                    "description": m.description,
                    "version": m.version,
                    "enabled": m.enabled,
                    "lifecycle": m.lifecycle,
                    "cli_modes": m.cli_modes,
                    "main_script": m.main_script,
                    "plugin_dir": str(m.plugin_dir),
                },
                "config": cfg,
            },
        }

    @app.patch("/v1/plugins/{plugin_id}")
    async def v1_plugin_patch(plugin_id: str, body: PluginStateUpdateRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        ok = loader.set_enabled(plugin_id, body.enabled)
        if not ok:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        op_id = f"op_{uuid.uuid4().hex[:12]}"
        plugin_ops[op_id] = {
            "operation_id": op_id,
            "plugin_id": plugin_id,
            "type": "set_enabled",
            "status": "done",
            "result": {"enabled": body.enabled},
            "ts": _utc_now(),
        }
        return {"ok": True, "trace_id": trace_id, "data": plugin_ops[op_id]}

    @app.get("/v1/plugins/{plugin_id}/config")
    async def v1_plugin_config_get(plugin_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        cfg_path = _plugin_config_path(m)
        cfg: dict[str, Any] = {}
        if cfg_path.is_file():
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                cfg = raw
        return {"ok": True, "trace_id": trace_id, "data": {"plugin_id": m.id, "config": cfg}}

    @app.put("/v1/plugins/{plugin_id}/config")
    async def v1_plugin_config_put(plugin_id: str, body: PluginConfigUpdateRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        cfg_path = _plugin_config_path(m)
        cfg_path.write_text(
            yaml.safe_dump(body.config or {}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        op_id = f"op_{uuid.uuid4().hex[:12]}"
        plugin_ops[op_id] = {
            "operation_id": op_id,
            "plugin_id": plugin_id,
            "type": "save_config",
            "status": "done",
            "ts": _utc_now(),
        }
        return {"ok": True, "trace_id": trace_id, "data": plugin_ops[op_id]}

    @app.post("/v1/plugins/{plugin_id}/reload")
    async def v1_plugin_reload(plugin_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        op_id = f"op_{uuid.uuid4().hex[:12]}"
        plugin_ops[op_id] = {
            "operation_id": op_id,
            "plugin_id": plugin_id,
            "type": "reload",
            "status": "done",
            "note": "manifest/config reloaded from disk on next runtime cycle",
            "ts": _utc_now(),
        }
        return {"ok": True, "trace_id": trace_id, "data": plugin_ops[op_id]}

    @app.post("/v1/plugins/{plugin_id}/restart")
    async def v1_plugin_restart(plugin_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        op_id = f"op_{uuid.uuid4().hex[:12]}"
        plugin_ops[op_id] = {
            "operation_id": op_id,
            "plugin_id": plugin_id,
            "type": "restart",
            "status": "done",
            "note": "manual restart requested; resident plugin restarts on process restart",
            "ts": _utc_now(),
        }
        return {"ok": True, "trace_id": trace_id, "data": plugin_ops[op_id]}

    @app.post("/v1/plugins/{plugin_id}/invoke")
    async def v1_plugin_invoke(plugin_id: str, body: PluginInvokeRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        loader = PluginLoader(root)
        m = _find_manifest(loader, plugin_id)
        if m is None:
            raise ApiError("not_found", f"Plugin not found: {plugin_id}", 404)
        if m.lifecycle != "on_demand":
            raise ApiError("bad_request", "invoke supported only for lifecycle=on_demand plugins", 400)
        mod = loader.import_plugin_module(m)
        ctx = PluginContext(root=root, config=config, agent=None)
        if callable(getattr(mod, "invoke_plugin", None)):
            result = await asyncio.to_thread(mod.invoke_plugin, body.payload, ctx)
        else:
            result = await asyncio.to_thread(run_plugin_entrypoint, mod, ctx)
        op_id = f"op_{uuid.uuid4().hex[:12]}"
        plugin_ops[op_id] = {
            "operation_id": op_id,
            "plugin_id": plugin_id,
            "type": "invoke",
            "status": "done",
            "ts": _utc_now(),
        }
        return {"ok": True, "trace_id": trace_id, "data": {"operation": plugin_ops[op_id], "result": result}}

    @app.get("/v1/plugins/operations/{operation_id}")
    async def v1_plugin_op(operation_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        row = plugin_ops.get(operation_id)
        if row is None:
            raise ApiError("not_found", f"Operation not found: {operation_id}", 404)
        return {"ok": True, "trace_id": trace_id, "data": row}

    @app.get("/v1/llm/balance")
    async def v1_llm_balance(request: Request, _: None = Depends(_auth_dep)):
        from core.llm_profile import resolve_openai_compatible_connection
        from core.openrouter_balance import fetch_openrouter_key_usage

        trace_id = _trace_id(request)
        conn = resolve_openai_compatible_connection(config)
        if conn.provider.lower() != "openrouter":
            return {
                "ok": True,
                "trace_id": trace_id,
                "data": {
                    "provider": conn.provider,
                    "openrouter": None,
                    "hint": "Баланс OpenRouter доступен при провайдере openrouter (BACKEND / llm.provider).",
                },
            }
        key = (conn.api_key or "").strip()
        if not key or key == "ollama":
            raise ApiError("config_error", "OpenRouter API key is not configured", 503)
        raw = await fetch_openrouter_key_usage(key)
        err = raw.get("_error")
        if err:
            if err == "missing_api_key":
                raise ApiError("config_error", "OpenRouter API key is not configured", 503)
            detail = raw.get("body") or raw.get("detail") or str(err)
            raise ApiError("openrouter_error", str(detail)[:600], 502)
        out = {k: v for k, v in raw.items() if not str(k).startswith("_")}
        return {"ok": True, "trace_id": trace_id, "data": {"provider": "openrouter", **out}}

    def _safe_set(cfg: dict, path: str, value: Any) -> None:
        keys = path.split(".")
        cur = cfg
        for k in keys[:-1]:
            nxt = cur.get(k)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[k] = nxt
            cur = nxt
        cur[keys[-1]] = value

    @app.post("/v1/config/update")
    async def v1_config_update(body: ConfigUpdateRequest, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        allowed = {
            "openrouter.model",
            "openrouter.temperature",
            "openrouter.top_p",
            "llm.model",
            "llm.provider",
            "llm.base_url",
            "health_monitor.enabled",
            "health_monitor.interval_seconds",
        }
        updates_applied: dict[str, Any] = {}
        for k, v in body.updates.items():
            if k not in allowed:
                raise ApiError("forbidden_update", f"Path not allowed: {k}", 403)
            _safe_set(config, k, v)
            updates_applied[k] = v
        return {"ok": True, "trace_id": trace_id, "data": {"updated": updates_applied}}

    @app.post("/v1/backup/run")
    async def v1_backup_run(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        res = await asyncio.to_thread(backup_manager.run_backup, "api_manual")
        return {"ok": True, "trace_id": trace_id, "data": res}

    @app.post("/v1/webhooks/out/routes")
    async def v1_webhooks_route_create(
        body: WebhookRouteCreateRequest,
        request: Request,
        _: None = Depends(_auth_dep),
    ):
        trace_id = _trace_id(request)
        row = await webhook_store.upsert_route(
            {
                "route_id": body.route_id or "",
                "event_type": body.event_type,
                "target_url": body.target_url,
                "secret": body.secret,
                "enabled": body.enabled,
                "max_retries": body.max_retries,
            }
        )
        return {"ok": True, "trace_id": trace_id, "data": row}

    @app.get("/v1/webhooks/out/routes")
    async def v1_webhooks_route_list(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        rows = await webhook_store.list_routes()
        return {"ok": True, "trace_id": trace_id, "data": {"routes": rows}}

    @app.patch("/v1/webhooks/out/routes/{route_id}")
    async def v1_webhooks_route_patch(
        route_id: str,
        body: WebhookRouteUpdateRequest,
        request: Request,
        _: None = Depends(_auth_dep),
    ):
        trace_id = _trace_id(request)
        current = await webhook_store.get_route(route_id)
        if current is None:
            raise ApiError("not_found", f"Route not found: {route_id}", 404)
        source_state = webhook_store._state["routes"].get(route_id, {})
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        merged = {**source_state, **updates, "route_id": route_id}
        row = await webhook_store.upsert_route(merged)
        return {"ok": True, "trace_id": trace_id, "data": row}

    @app.delete("/v1/webhooks/out/routes/{route_id}")
    async def v1_webhooks_route_delete(route_id: str, request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        ok = await webhook_store.delete_route(route_id)
        if not ok:
            raise ApiError("not_found", f"Route not found: {route_id}", 404)
        return {"ok": True, "trace_id": trace_id, "data": {"deleted": True, "route_id": route_id}}

    @app.post("/v1/webhooks/out/test/{route_id}")
    async def v1_webhooks_route_test(
        route_id: str,
        body: WebhookTestRequest,
        request: Request,
        _: None = Depends(_auth_dep),
    ):
        trace_id = _trace_id(request)
        route = webhook_store._state["routes"].get(route_id)
        if not isinstance(route, dict):
            raise ApiError("not_found", f"Route not found: {route_id}", 404)
        payload = {
            "event_type": route.get("event_type"),
            "source": "manual_test",
            "payload": body.payload,
            "ts": _utc_now(),
        }
        row = await _dispatch_webhook(webhook_store, route, payload, source="manual_test")
        return {"ok": True, "trace_id": trace_id, "data": row}

    @app.get("/v1/webhooks/deliveries")
    async def v1_webhooks_deliveries(
        request: Request,
        status: Optional[str] = Query(default=None),
        _: None = Depends(_auth_dep),
    ):
        trace_id = _trace_id(request)
        rows = await webhook_store.list_deliveries((status or "").strip())
        return {"ok": True, "trace_id": trace_id, "data": {"deliveries": rows}}

    @app.post("/v1/webhooks/deliveries/{delivery_id}/retry")
    async def v1_webhooks_delivery_retry(
        delivery_id: str,
        body: WebhookRetryRequest,
        request: Request,
        _: None = Depends(_auth_dep),
    ):
        trace_id = _trace_id(request)
        row = await webhook_store.get_delivery(delivery_id)
        if row is None:
            raise ApiError("not_found", f"Delivery not found: {delivery_id}", 404)
        route_id = str(row.get("route_id") or "")
        route = webhook_store._state["routes"].get(route_id)
        if not isinstance(route, dict):
            raise ApiError("not_found", f"Route not found for delivery: {route_id}", 404)
        if body.delay_seconds > 0:
            await asyncio.sleep(body.delay_seconds)
        redelivered = await _dispatch_webhook(
            webhook_store,
            route,
            row.get("payload") or {},
            source="manual_retry",
        )
        return {"ok": True, "trace_id": trace_id, "data": redelivered}

    @app.get("/v1/webhooks/dlq")
    async def v1_webhooks_dlq(request: Request, _: None = Depends(_auth_dep)):
        trace_id = _trace_id(request)
        rows = await webhook_store.list_dlq()
        return {"ok": True, "trace_id": trace_id, "data": {"items": rows}}

    async def _handle_inbound(provider: str, endpoint_id: str, request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                payload = {"raw": payload}
        except Exception:
            text = await request.body()
            payload = {"raw_text": text.decode("utf-8", errors="replace")}
        source = f"webhook.{provider}"
        ev = CoreEvent(
            event_type=f"webhook.{provider}.inbound",
            source=source,
            payload={
                "endpoint_id": endpoint_id,
                "provider": provider,
                "headers": dict(request.headers),
                "payload": payload,
                "received_at": _utc_now(),
            },
        )
        agent.event_bus.publish(ev)
        # Basic bridge: if payload has text/message, pass into agent chat.
        txt = str(
            payload.get("text")
            or payload.get("message")
            or payload.get("content")
            or ""
        ).strip()
        chat_reply = ""
        if txt:
            chat_reply = await agent.chat(
                user_message=txt,
                username=str(payload.get("username") or f"{provider}_user"),
                discord_user_id=str(payload.get("user_id") or ""),
                channel_id=str(payload.get("channel_id") or f"{provider}:{endpoint_id}"),
            )
        return {"accepted": True, "provider": provider, "endpoint_id": endpoint_id, "reply": chat_reply}

    @app.post("/v1/webhooks/in/{provider}/{endpoint_id}")
    async def v1_webhooks_inbound(provider: str, endpoint_id: str, request: Request):
        trace_id = _trace_id(request)
        out = await _handle_inbound(provider, endpoint_id, request)
        return {"ok": True, "trace_id": trace_id, "data": out}

    @app.get("/v1/webhooks/in/{provider}/{endpoint_id}/health")
    async def v1_webhooks_inbound_health(provider: str, endpoint_id: str):
        return {"ok": True, "trace_id": str(uuid.uuid4()), "data": {"provider": provider, "endpoint_id": endpoint_id, "status": "ready"}}

    @app.websocket("/v1/ws/chat")
    async def ws_chat(
        websocket: WebSocket,
        token: Optional[str] = Query(default=None),
    ):
        trace_id = str(uuid.uuid4())
        authorization = websocket.headers.get("authorization")
        try:
            _require_ws_auth(token, authorization, config)
        except ApiError:
            # 1008: Policy Violation
            await websocket.close(code=1008, reason="unauthorized")
            return
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "hello",
                "trace_id": trace_id,
                "protocol": "neyra.ws.chat.v1",
                "ping_interval_seconds": ws_ping_interval,
                "idle_timeout_seconds": ws_idle_timeout,
            }
        )
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=ws_idle_timeout)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "error", "code": "idle_timeout", "trace_id": trace_id})
                await asyncio.sleep(ws_close_grace)
                await websocket.close(code=1000, reason="idle timeout")
                break
            except WebSocketDisconnect:
                break
            except Exception:
                await websocket.send_json({"type": "error", "code": "bad_payload", "trace_id": trace_id})
                continue

            kind = str(msg.get("type") or "").strip().lower()
            if kind == "ping":
                await websocket.send_json({"type": "pong", "ts": datetime.now().isoformat(), "trace_id": trace_id})
                continue
            if kind != "chat":
                await websocket.send_json({"type": "error", "code": "unknown_type", "trace_id": trace_id})
                continue

            text = str(msg.get("text") or "").strip()
            if not text:
                await websocket.send_json({"type": "error", "code": "empty_text", "trace_id": trace_id})
                continue
            username = str(msg.get("username") or "ws_user")
            platform_user_id = str(msg.get("platform_user_id") or "")
            channel_id = str(msg.get("channel_id") or "ws")

            try:
                async for chunk in agent.chat_stream(
                    text,
                    username=username,
                    discord_user_id=platform_user_id,
                    channel_id=channel_id,
                ):
                    if chunk.get("type") == "token":
                        await websocket.send_json(
                            {"type": "token", "text": chunk.get("text", ""), "trace_id": trace_id}
                        )
                    elif chunk.get("type") == "done":
                        await websocket.send_json(
                            {
                                "type": "done",
                                "text": chunk.get("text", ""),
                                "sounds": chunk.get("sounds", []),
                                "trace_id": trace_id,
                            }
                        )
                    elif chunk.get("type") == "error":
                        await websocket.send_json(
                            {"type": "error", "code": "chat_error", "message": chunk.get("text", ""), "trace_id": trace_id}
                        )
            except WebSocketDisconnect:
                break
            except Exception as e:
                await websocket.send_json({"type": "error", "code": "internal_chat_error", "message": str(e), "trace_id": trace_id})

    @app.websocket("/v1/ws/audio")
    async def ws_audio(
        websocket: WebSocket,
        token: Optional[str] = Query(default=None),
    ):
        """
        Minimal bidirectional audio stream endpoint.
        Accepts binary audio chunks and emits lightweight interim/final events.
        (STT provider adapters are handled in 5.2; here is the gateway contract.)
        """
        trace_id = str(uuid.uuid4())
        authorization = websocket.headers.get("authorization")
        try:
            _require_ws_auth(token, authorization, config)
        except ApiError:
            await websocket.close(code=1008, reason="unauthorized")
            return
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "hello",
                "trace_id": trace_id,
                "protocol": "neyra.ws.audio.v1",
                "ping_interval_seconds": ws_ping_interval,
                "idle_timeout_seconds": ws_idle_timeout,
            }
        )
        chunk_count = 0
        bytes_total = 0
        while True:
            try:
                packet = await asyncio.wait_for(websocket.receive(), timeout=ws_idle_timeout)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "error", "code": "idle_timeout", "trace_id": trace_id})
                await asyncio.sleep(ws_close_grace)
                await websocket.close(code=1000, reason="idle timeout")
                break
            except WebSocketDisconnect:
                break

            if packet.get("type") == "websocket.disconnect":
                break

            text_data = packet.get("text")
            if text_data:
                try:
                    msg = json.loads(text_data)
                except Exception:
                    msg = {}
                kind = str(msg.get("type") or "").strip().lower()
                if kind == "ping":
                    await websocket.send_json({"type": "pong", "ts": datetime.now().isoformat(), "trace_id": trace_id})
                    continue
                if kind == "commit":
                    await websocket.send_json(
                        {
                            "type": "transcript.final",
                            "text": f"[stub] received {chunk_count} chunks / {bytes_total} bytes",
                            "trace_id": trace_id,
                        }
                    )
                    chunk_count = 0
                    bytes_total = 0
                    continue
                await websocket.send_json({"type": "error", "code": "unknown_type", "trace_id": trace_id})
                continue

            data = packet.get("bytes")
            if data:
                chunk_count += 1
                bytes_total += len(data)
                # Lightweight interim event to keep stream alive.
                if chunk_count % 5 == 0:
                    await websocket.send_json(
                        {
                            "type": "transcript.interim",
                            "text": f"[stub] audio chunks: {chunk_count}",
                            "trace_id": trace_id,
                        }
                    )

    dash_cfg = config.get("dashboard") or {}
    if bool(dash_cfg.get("enabled", True)):
        dist = _dashboard_dist_path(config)
        if dist.is_dir() and (dist / "index.html").is_file():
            app.mount("/", StaticFiles(directory=str(dist), html=True), name="neyra_dashboard")
            logger.info("Serving dashboard from %s", dist)
        else:
            logger.warning(
                "Dashboard enabled but no build at %s — only API (run: cd frontend && npm install && npm run build).",
                dist,
            )

    return app


def run_internal_api(config: dict) -> None:
    """Точка входа плагина `api`: делегирует в ядро `core.server.run_neyra_server`."""
    from core.server import run_neyra_server

    run_neyra_server(config)
