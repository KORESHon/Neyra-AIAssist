<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# REST Endpoints

## Core
- `POST /v1/chat`
- `POST /v1/memory/search`
- `POST /v1/memory/write`
- `POST /v1/notify`
- `GET /v1/health`
- `GET /v1/memory/stats`
- `GET /v1/llm/balance`
- `POST /v1/config/update`
- `POST /v1/backup/run`

## Plugins
- `GET /v1/plugins`
- `GET /v1/plugins/{plugin_id}`
- `PATCH /v1/plugins/{plugin_id}` (`enabled`)
- `GET /v1/plugins/{plugin_id}/config`
- `PUT /v1/plugins/{plugin_id}/config`
- `POST /v1/plugins/{plugin_id}/reload`
- `POST /v1/plugins/{plugin_id}/restart`
- `POST /v1/plugins/{plugin_id}/invoke`
- `GET /v1/plugins/operations/{operation_id}`

## Webhooks
- `POST /v1/webhooks/in/{provider}/{endpoint_id}`
- `GET /v1/webhooks/in/{provider}/{endpoint_id}/health`
- `POST /v1/webhooks/out/routes`
- `GET /v1/webhooks/out/routes`
- `PATCH /v1/webhooks/out/routes/{route_id}`
- `DELETE /v1/webhooks/out/routes/{route_id}`
- `POST /v1/webhooks/out/test/{route_id}`
- `GET /v1/webhooks/deliveries`
- `POST /v1/webhooks/deliveries/{delivery_id}/retry`
- `GET /v1/webhooks/dlq`