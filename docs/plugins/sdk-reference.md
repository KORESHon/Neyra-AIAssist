# SDK Reference

## `PluginContext`
- `root`: путь к проекту.
- `config`: merged runtime config.
- `agent`: доступен там, где нужен общий агент (например Discord).

## Entrypoint
- Модуль плагина должен экспортировать:
  - `run_plugin(ctx: PluginContext) -> None`

## Вызов
- Core lifecycle: через `core/server.py`.
- On-demand: через `scripts/invoke_plugin.py` или API invoke.
