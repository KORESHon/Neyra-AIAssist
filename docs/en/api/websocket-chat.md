<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# WebSocket Chat

Endpoint: `ws://127.0.0.1:8787/v1/ws/chat`

## Клиент -> сервер
- `{"type":"ping"}`
- `{"type":"chat","text":"...","username":"...","platform_user_id":"...","channel_id":"..."}`

## Сервер -> клиент
- `hello`
- `pong`
- `token` (stream chunk)
- `done` (финал + sounds)
- `error`