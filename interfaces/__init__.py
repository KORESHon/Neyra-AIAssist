"""
Interfaces package: плагины в interfaces/<plugin_id>/ (plugin.yaml + main.py).

Обычный запуск: `python main.py` — ядро (`core/server.py`): HTTP, дашборд, resident-плагины.
Отдельно: `python main.py --mode model` — только консоль. Поле cli_modes — реестр PluginLoader и алиасы CLI.
"""

__all__ = []
