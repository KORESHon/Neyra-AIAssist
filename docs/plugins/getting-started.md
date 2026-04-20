# Getting Started: Plugin

1. Скопируйте шаблон из `interfaces/000EXAMPLE/`.
2. Заполните `plugin.yaml`.
3. Реализуйте `run_plugin(ctx)` в `main.py`.
4. Добавьте `config.example.yaml`.
5. Проверка:
   - `python scripts/invoke_plugin.py <plugin_id>` для on_demand
   - `python main.py` для resident
