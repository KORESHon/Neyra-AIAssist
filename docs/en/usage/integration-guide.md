# Гайд интегратора

## Через REST
- Отправляйте пользовательские сообщения в `POST /v1/chat`.
- Получайте контекстные события через `POST /v1/notify`.

## Через WebSocket
- Для потокового UX используйте `/v1/ws/chat`.
- Для аудио-кейсов используйте `/v1/ws/audio`.

## Через Webhooks
- Inbound: `POST /v1/webhooks/in/{provider}/{endpoint_id}`.
- Outbound: маршруты `event_type -> target_url` через `/v1/webhooks/out/routes`.
