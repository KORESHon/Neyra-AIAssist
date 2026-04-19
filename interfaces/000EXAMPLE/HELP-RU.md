# Neyra Plugin SDK — Туториал и справка (Русский)

**English:** [HELP.md](HELP.md)

Этот документ — и **учебник**, и **справочник**: философия плагинов, что можно и нельзя делать, пошаговый Hello World и ссылки на реальный код.

---

## Содержание

1. [Философия](#философия)
2. [Что можно делать (возможности)](#что-можно-делать-возможности)
3. [Чего нельзя делать (анти-паттерны)](#чего-нельзя-делать-анти-паттерны)
4. [Туториал: плагин Hello World](#туториал-плагин-hello-world)
5. [Справка: структура и манифест](#справка-структура-и-манифест)
6. [Справка: PluginContext и run_plugin](#справка-plugincontext-и-run_plugin)
7. [Как main.py подключает режимы CLI](#как-mainpy-подключает-режимы-cli)
8. [API загрузчика](#api-загрузчика)
9. [Эталонные реализации в репозитории](#эталонные-реализации-в-репозитории)
10. [Чеклист перед публикацией плагина](#чеклист-перед-публикацией-плагина)
11. [Частые проблемы](#частые-проблемы)

---

## Философия

**Плагин** — изолированная папка `interfaces/<имя>/`. Ядро находит все `interfaces/*/plugin.yaml` и подгружает Python-модуль по правилам `lifecycle`, `cli_modes` и будущих вызовов `invoke`. **После удаления папки плагина ядро должно продолжать работать** — это главное правило.

---

## Что можно делать (возможности)

Через `PluginContext` плагин может:

- **Добавлять интерфейсы (точки входа):** другой транспорт чата (Telegram, VK, локальный STT и т.д.) по аналогии с `discord_text`.
- **Работать как фоновые задачи:** периодические проверки (почта, RSS), запись фактов в память — с осторожностью к async и к тому, не блокировать общий процесс.
- **Поднимать свои серверы:** FastAPI/uvicorn внутри процесса, как `internal_api` (`api_server.py`).
- **Использовать ядро:** читать `ctx.config`; для LLM использовать переданный `ctx.agent` (как в Discord) или создавать `NeyraAgent(ctx.config)` внутри плагина (как в Internal API). Прямые вызовы облачного SDK в обход `NeyraAgent` для ответов ассистента **не рекомендуются** — теряются единая конфигурация, логирование и политики.

---

## Чего нельзя делать (анти-паттерны)

| Нельзя | Почему |
|--------|--------|
| **Менять файлы в `core/` из плагина** | Плагин должен удаляться без поломки ядра. Вся логика — в `interfaces/<ваш_плагин>/`. |
| **Хранить секреты в `plugin.yaml` или в коде** | Токены — в `.env`, подстановка в `ctx.config` через `core/secrets_loader.py`. |
| **Блокировать event loop без нужды** | Для фоновой работы в общем процессе — `asyncio` и неблокирующий I/O. Отдельные CLI-режимы (Discord, uvicorn) могут блокировать поток по дизайну. |
| **Обходить NeyraAgent для ответов LLM** | Не подключать «голый» `openai` для реплик ассистента — используйте `NeyraAgent`. |
| **Занимать чужие `cli_modes`** | Не регистрируйте для экспериментов имена `discord`, `api` и т.д. — выберите уникальное имя режима. |

---

## Туториал: плагин Hello World

### Шаг 1 — Создайте папку

```text
interfaces/my_hello_plugin/
```

Имя папки должно быть уникальным (удобно: строчные буквы и подчёркивания).

### Шаг 2 — Добавьте `plugin.yaml`

```yaml
id: hello_world
name: Hello World Plugin
description: Минимальная демонстрация SDK
version: "1.0.0"
enabled: true
lifecycle: on_demand
cli_modes:
  - hello
main_script: main.py
```

### Шаг 3 — Создайте `main.py` в корне плагина

У `NeyraAgent` метод `chat` — **асинхронный**. В синхронной `run_plugin` используйте `asyncio.run`. В текущем `main.py` репозитория **`ctx.agent` передаётся только в режиме Discord**; для других режимов создайте агент внутри плагина (как в `internal_api`).

```python
from __future__ import annotations

import asyncio

from core.agent import NeyraAgent
from core.plugin_sdk import PluginContext


def run_plugin(ctx: PluginContext) -> None:
    print(f"[hello_world] корень проекта: {ctx.root}")

    async def _run() -> None:
        agent = ctx.agent or NeyraAgent(ctx.config)
        out = await agent.chat(
            "Ответь одним коротким предложением по-русски: привет из туториала плагина.",
            username="hello_world",
        )
        print("[hello_world] ответ модели:", (out or {}).get("text", out))

    asyncio.run(_run())
```

### Шаг 4 — Запуск

```bash
python main.py --mode hello
```

Если два плагина объявят один и тот же режим в `cli_modes`, загрузчик оставит один из них (в лог будет предупреждение). Для своих тестов выбирайте **уникальное** имя режима.

### Шаблон `000EXAMPLE`

Каталог `interfaces/000EXAMPLE/` в репозитории по умолчанию с **`enabled: false`** и **без** `cli_modes`, чтобы не пересекаться с вашими режимами. Его можно копировать или ориентироваться на структуру выше.

---

## Справка: структура и манифест

Типичная структура:

```text
interfaces/000EXAMPLE/
  plugin.yaml
  HELP.md
  HELP-RU.md
  help.html
  core/
    main.py
```

Готовые интерфейсы: `discord_text/`, `internal_api/`, `local_voice/`, `laptop_screen/`.

### Поля `plugin.yaml`

| Поле | Описание |
|------|----------|
| `id` | Уникальный строковый идентификатор. |
| `name`, `description`, `version` | Метаданные для реестра и UI. |
| `enabled` | При `false` запуск `python main.py --mode …` для этого режима завершится ошибкой. |
| `lifecycle` | `resident` / `on_demand` — влияет на предзагрузку (см. загрузчик). |
| `cli_modes` | Список имён для `python main.py --mode <имя>`. Пустой — только программная загрузка позже. |
| `main_script` | Путь к файлу `.py` относительно папки плагина. |

Поля `events`, `commands`, `permissions` зарезервированы под будущий SDK и мини-сайт.

---

## Справка: PluginContext и run_plugin

В модуле `main_script` нужно экспортировать:

```python
def run_plugin(ctx: PluginContext) -> None:
    ...
```

`PluginContext` (`core/plugin_sdk.py`):

- `root` — корень репозитория (`Path`);
- `config` — полный конфиг после подстановки секретов из `.env`;
- `agent` — экземпляр `NeyraAgent` или `None` (сейчас `main.py` передаёт агент только для **Discord**; в остальных режимах создавайте `NeyraAgent(ctx.config)` при необходимости).

Функция может быть блокирующей (как `bot.run()` или `uvicorn.run()`).

---

## Как main.py подключает режимы CLI

- `PluginLoader.manifest_for_cli_mode(mode)` находит плагин, у которого в `cli_modes` есть `mode`.
- Если манифест не найден или `enabled: false` — ошибка запуска.
- Модуль загружается через `import_plugin_module`, затем вызывается `run_plugin_entrypoint` → `run_plugin(ctx)`.

---

## API загрузчика

- `core/plugin_loader.py` — `PluginLoader`, `discover_manifests()`, `list_plugins()`, `cli_mode_index()`, `import_plugin_module()`, `manifest_for_cli_mode()`, `set_enabled()`.
- `core/plugin_sdk.py` — `PluginContext`, `run_plugin_entrypoint`.

---

## Эталонные реализации в репозитории

| Плагин | Назначение |
|--------|------------|
| `interfaces/discord_text/` | Discord, использует переданный `ctx.agent`. |
| `interfaces/internal_api/` | FastAPI + uvicorn, свой `NeyraAgent` в `build_app`. |
| `interfaces/local_voice/`, `interfaces/laptop_screen/` | Заглушки под будущую реализацию. |

---

## Чеклист перед публикацией плагина

- [ ] Нет секретов в репозитории — только `.env`, ключи описаны в `.env.example`.
- [ ] Уникальные `id` и уникальные значения в `cli_modes` относительно других плагинов.
- [ ] Значение `enabled` осмысленно для чужих клонов (`false`, если без локальных секретов не заведётся).
- [ ] Ответы ассистента идут через `NeyraAgent` (кроме редких задокументированных исключений).
- [ ] Краткая инструкция в README или отсылка к HELP для установки в `interfaces/`.

---

## Частые проблемы

**«Нет плагина для режима»** — проверьте орфографию в `cli_modes` и `enabled: true`.

**Ошибки импорта** — запускайте из корня проекта; структура как у встроенных плагинов.

**`agent` равен `None`** — для режимов кроме Discord это норма; используйте `NeyraAgent(ctx.config)` внутри плагина.

**Предупреждение о дубликате режима** — два манифеста объявили один и тот же `cli_modes`; переименуйте режим.
