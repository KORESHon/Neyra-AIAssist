"""
Interfaces package: плагины лежат в interfaces/<plugin_id>/ (plugin.yaml + main.py).

Точка входа процесса: python main.py --mode <cli_mode>; соответствие mode → плагин задаётся
в plugin.yaml полем cli_modes.
"""

__all__ = []
