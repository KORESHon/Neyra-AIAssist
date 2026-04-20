# Config и секреты плагинов

- Параметры плагина: `interfaces/<id>/config.yaml`.
- Секреты: `.env` и `core/secrets_loader.py`.
- Не храните токены в `config.yaml` плагина.

## Merge
`core/plugin_config.py` подмешивает plugin config в общий runtime dict до подстановки env secrets.
