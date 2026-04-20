# Тестирование плагинов

## Smoke
- `python scripts/invoke_plugin.py <plugin_id>`
- `python scripts/healthcheck.py --mode core`

## Рекомендации
- Unit tests для функций трансформации payload.
- Интеграционный тест на корректный `run_plugin(ctx)`.
- Таймауты и обработка ошибок должны быть явными.
