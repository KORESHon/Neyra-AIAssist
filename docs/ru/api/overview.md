<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

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