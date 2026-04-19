"""
Internal API (v1) for Neyra core.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.agent import NeyraAgent
from core.backup_manager import BackupManager
from core.event_bus import CoreEvent
from core.health_monitor import HealthMonitor

logger = logging.getLogger("neyra.api")


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


def build_app(config: dict) -> FastAPI:
    app = FastAPI(title="Neyra Internal API", version="1.0")
    agent = NeyraAgent(config)
    monitor = HealthMonitor(config)
    backup_manager = BackupManager(config)
    app.state.agent = agent
    app.state.monitor = monitor
    app.state.backup_manager = backup_manager
    app.state.config = config
    ws_cfg = (config.get("internal_api") or {}).get("websocket") or {}
    ws_idle_timeout = max(5, int(ws_cfg.get("idle_timeout_seconds", 60)))
    ws_ping_interval = max(2, int(ws_cfg.get("ping_interval_seconds", 20)))
    ws_close_grace = max(1, int(ws_cfg.get("close_grace_seconds", 5)))

    @app.on_event("startup")
    async def _startup() -> None:
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

    return app


def run_internal_api(config: dict) -> None:
    import uvicorn

    api_cfg = config.get("internal_api") or {}
    host = str(api_cfg.get("host") or "127.0.0.1")
    port = int(api_cfg.get("port") or 8787)
    app = build_app(config)
    uvicorn.run(app, host=host, port=port, log_level="info")
