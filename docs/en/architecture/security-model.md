# Модель безопасности

## Базовые границы
- Internal API локальный по умолчанию (`127.0.0.1`).
- Bearer авторизация включается через `INTERNAL_API_TOKEN`.
- Секреты не хранятся в `config.yaml`.

## Webhooks
- Для outbound маршрутов можно задавать `secret`.
- Логи доставок и DLQ ведутся в `logs/webhooks_state.json`.

## Рекомендации
- В проде включать `INTERNAL_API_TOKEN`.
- Заворачивать API за reverse proxy + TLS.
- Ограничивать входящий доступ firewall/IP allowlist.
- Регулярно ротировать ключи (`OPENROUTER_API_KEY`, `DISCORD_TOKEN` и др.).
