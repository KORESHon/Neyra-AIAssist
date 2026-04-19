"""
Interfaces package: плагины в interfaces/<plugin_id>/ (plugin.yaml + main.py).

Обычный запуск: `python main.py` — ядро (`core/server.py`): HTTP, дашборд, resident-плагины.
Консоль: `python main.py --mode console`. Поле `cli_modes` в манифестах опционально (invoke/совместимость).
"""

__all__ = []
