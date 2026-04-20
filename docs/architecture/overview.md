# Архитектура Neyra

Neyra состоит из стабильного ядра и плагинов в `interfaces/`.

## Слои
- `core/`: агент, память, рефлексия, event bus, health monitor.
- `interfaces/internal_api/`: HTTP API + WebSocket + отдача frontend.
- `interfaces/discord_text/`: resident Discord interface.
- `interfaces/*`: расширения через plugin SDK.

## Поток данных
1. `main.py` загружает `config.yaml`.
2. `core/plugin_config.py` подмешивает `interfaces/<id>/config.yaml`.
3. `core/secrets_loader.py` подставляет секреты из `.env`.
4. `core/server.py` запускает FastAPI и resident-плагины.
5. UI и внешние клиенты работают через `/v1` и `/v1/ws/*`.

## Принципы
- Вкл/выкл плагина: только `plugin.yaml`.
- Настройки плагина: `interfaces/<id>/config.yaml`.
- Секреты: только `.env`.
