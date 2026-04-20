# PLAN.md — Roadmap and Status

## 1) Current release status


| Area              | Status              | Notes                                                                                |
| ----------------- | ------------------- | ------------------------------------------------------------------------------------ |
| Core runtime      | Done                | Stable `core` and `console` modes, merged plugin config model, env-driven secrets    |
| Internal API + WS | Done                | REST + WebSocket endpoints served from `interfaces/internal_api/api_server.py`       |
| Micro-site        | Done                | Multi-page frontend: Home, Dashboard, Plugins, Settings, Webhooks, API Docs          |
| Plugin management | Done                | API + UI: enable/disable, config read/write, reload/restart/invoke, operation status |
| Webhooks          | Done (MVP)          | Inbound endpoints + outbound routes + deliveries + DLQ + manual retry/test           |
| Documentation     | Done (restructured) | Full docs portal split into RU/EN trees                                              |


## 2) Done in this cycle

### Product and UI

- Reworked frontend into a real micro-site/control center.
- Embedded API docs directly in the panel (Swagger/ReDoc/OpenAPI).
- Added UI workflows for plugins, runtime settings and webhooks.

### Backend and API

- Added full plugin-management endpoints under `/v1/plugins/*`.
- Added webhook-management endpoints under `/v1/webhooks/*`.
- Added delivery tracking and DLQ flow for outbound webhooks.

### Config and operations

- Kept plugin state in `plugin.yaml`; plugin settings in `interfaces/<id>/config.yaml`.
- Kept secrets in `.env`.
- Preserved health checks and build/smoke verification.

### Documentation

- Added complete docs structure and language split (`docs/ru/**`, `docs/en/**`).
- Updated root documentation entrypoints and frontend README.

## 3) Next priorities

1. Browser chat page (full UX on top of `/v1/ws/chat`).
2. GitHub Pages public demo (BYOK + safe public mode).
3. Security hardening for webhook signatures/provider-specific verification and stricter rate limiting.
4. Voice/Screen/Music implementation (current plugins are stubs except core integrations).

## 4) Validation checklist

- Backend syntax: `python -m compileall -q core interfaces scripts main.py`
- Frontend build: `cd frontend && npm run build`
- Core smoke: `python scripts/healthcheck.py --mode core --skip-http`

## 5) Backlog

- Desktop and mobile-lite clients.
- AI-station device mode.
- Open-core extension model.

