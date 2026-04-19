# Neyra Plugin SDK — справка / Help

**Languages:** [Русский](#русский) · [English](#english)

---

## Русский

### Что такое плагин

Плагин — это каталог в `interfaces/<имя_папки>/` с обязательным файлом **`plugin.yaml`** и точкой входа **`main_script`** (по умолчанию `core/main.py` или `main.py`). Ядро находит все `interfaces/*/plugin.yaml`, строит реестр и при необходимости загружает Python-модуль.

### Рекомендуемая структура (пример)

```
interfaces/000EXAMPLE/
  plugin.yaml          # манифест
  HELP.md              # эта справка (Markdown, удобно на GitHub)
  help.html            # та же логика в виде HTML для просмотра в браузере с диска
  core/
    main.py            # main_script — экспорт run_plugin(ctx)
```

Реальные интерфейсы в репозитории: `discord_text/`, `internal_api/`, `local_voice/`, `laptop_screen/`.

### Поля `plugin.yaml`

| Поле | Описание |
|------|-----------|
| `id` | Уникальный id плагина (строка). |
| `name`, `description`, `version` | Метаданные для реестра и UI. |
| `enabled` | `true` / `false` — участвует ли плагин в рантайме. |
| `lifecycle` | `resident` — прелоад в списке «загруженных» при обходе resident; `on_demand` — код не импортируется до вызова / CLI. |
| `cli_modes` | Список строк, совпадающих с `python main.py --mode <имя>`. Пустой список — плагин не привязан к отдельному режиму. |
| `main_script` | Путь к `.py` относительно папки плагина (например `core/main.py`). |

Дополнительные поля (`events`, `commands`, …) зарезервированы под будущий SDK и мини-сайт.

### Контракт Python: `PluginContext` и `run_plugin`

Модуль `main_script` **обязан** экспортировать:

```python
def run_plugin(ctx: PluginContext) -> None:
    ...
```

`PluginContext` (`core/plugin_sdk.py`):

- `root` — `Path` корня проекта;
- `config` — полный словарь конфигурации после подстановки секретов из `.env`;
- `agent` — экземпляр `NeyraAgent` или `None` (для Discord передаётся агент; для HTTP API плагин обычно создаёт свой агент внутри, как `internal_api`).

Функция может блокировать поток (как `discord.py` `run()` или `uvicorn.run()`).

### Связь с `main.py`

- Режимы CLI задаются через **`cli_modes`** в манифесте.
- Команда: `python main.py --mode discord` → плагин, у которого в `cli_modes` есть `discord`.
- Если плагин **`enabled: false`**, запуск режима завершится ошибкой.
- Пример шаблона **`000EXAMPLE`** по умолчанию выключен и **без** `cli_modes`, чтобы не пересекаться с боевыми режимами.

### Загрузчик

- `core/plugin_loader.py` — `PluginLoader`, `discover_manifests()`, `list_plugins()`, `import_plugin_module()`, `manifest_for_cli_mode()`.
- `core/plugin_sdk.py` — `run_plugin_entrypoint(module, ctx)`.

### Где смотреть рабочий код

- Текстовый Discord: `interfaces/discord_text/`.
- Internal API: `interfaces/internal_api/` (`api_server.py` — FastAPI-приложение).

---

## English

### What a plugin is

A plugin is a directory under `interfaces/<folder_name>/` with a required **`plugin.yaml`** and an entry module **`main_script`** (often `core/main.py` or `main.py`). The core discovers every `interfaces/*/plugin.yaml`, builds a registry, and loads the Python module when needed.

### Suggested layout (template)

```
interfaces/000EXAMPLE/
  plugin.yaml          # manifest
  HELP.md              # this guide (renders nicely on GitHub)
  help.html            # same content as HTML for local browser viewing
  core/
    main.py            # main_script — must export run_plugin(ctx)
```

Shipped interfaces: `discord_text/`, `internal_api/`, `local_voice/`, `laptop_screen/`.

### `plugin.yaml` fields

| Field | Meaning |
|-------|---------|
| `id` | Unique plugin id (string). |
| `name`, `description`, `version` | Metadata for registry / UI. |
| `enabled` | `true` / `false` — whether the plugin participates at runtime. |
| `lifecycle` | `resident` vs `on_demand` (see PLAN / loader: on_demand skips eager import where applicable). |
| `cli_modes` | List of names matching `python main.py --mode <name>`. Empty = no dedicated CLI mode. |
| `main_script` | Path to the entry `.py` relative to the plugin folder. |

Extra keys (`events`, `commands`, …) are reserved for future SDK and dashboard.

### Python contract: `PluginContext` and `run_plugin`

The `main_script` module **must** export:

```python
def run_plugin(ctx: PluginContext) -> None:
    ...
```

`PluginContext` (see `core/plugin_sdk.py`):

- `root` — project root `Path`;
- `config` — full config dict after `.env` overlays;
- `agent` — `NeyraAgent` instance or `None` (Discord gets an agent from `main.py`; the API plugin builds its own inside `build_app`, etc.).

The function may block (Discord / uvicorn).

### Wiring to `main.py`

- CLI modes come from **`cli_modes`** in the manifest.
- Example: `python main.py --mode api` → plugin whose `cli_modes` contains `api`.
- If the plugin is **`enabled: false`**, the mode exits with an error.
- The **`000EXAMPLE`** template stays **disabled** and has **no** `cli_modes` so it never collides with production modes.

### Loader API

- `core/plugin_loader.py` — discovery, `list_plugins()`, `import_plugin_module()`, `manifest_for_cli_mode()`.
- `core/plugin_sdk.py` — `run_plugin_entrypoint(module, ctx)`.

### Reference implementations

- Discord text bot: `interfaces/discord_text/`.
- HTTP / WebSocket API: `interfaces/internal_api/` (`api_server.py`).
