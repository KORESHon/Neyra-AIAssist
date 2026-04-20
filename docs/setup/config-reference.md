# Справочник config.yaml

`config.yaml` содержит только базовый runtime-конфиг ядра.

## Ключевые секции
- `assistant`
- `BACKEND`, `openrouter`, `llm`
- `vision`
- `memory`
- `voice_cloud`
- `health_monitor`
- `backup`, `external_storage`
- `logging`

## Вынесено в плагины
- `discord` -> `interfaces/discord_text/config.yaml`
- `internal_api`, `dashboard` -> `interfaces/internal_api/config.yaml`
- локальные plugin settings -> `interfaces/<id>/config.yaml`

## Запрещено хранить в yaml
- API keys и токены. Используйте `.env`.
