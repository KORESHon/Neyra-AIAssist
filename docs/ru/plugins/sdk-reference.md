<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

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