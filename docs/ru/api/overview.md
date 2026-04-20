# API Overview

Base URL: `http://127.0.0.1:8787`

## Формат ответов

- success: `{ "ok": true, "trace_id": "...", "data": ... }`
- error: `{ "ok": false, "trace_id": "...", "error": { "code": "...", "message": "..." } }`

## Авторизация

- Header: `Authorization: Bearer <token>`
- Для WS: `Authorization` или query `?token=...`
- Если `INTERNAL_API_TOKEN` пуст, auth отключена.

## Группы API

- chat, memory, notify, health, balance
- plugins management
- webhooks inbound/outbound
- backup and runtime config update