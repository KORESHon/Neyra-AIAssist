# Модель конфигурации

## Источники
1. Корневой `config.yaml`.
2. Файлы плагинов `interfaces/<id>/config.yaml`.
3. Секреты `.env`.

## Merge-порядок
1. Загружается `config.yaml`.
2. `merge_plugin_configs(...)` подмешивает конфиги плагинов.
3. `apply_env_secrets(...)` перекрывает секреты из окружения.

## Правила
- `discord_text` мержится в секцию `discord`.
- `internal_api` мержится в `internal_api` и `dashboard`.
- Прочие плагины мержатся в `plugins.<id>`.
