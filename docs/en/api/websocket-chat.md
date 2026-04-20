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
