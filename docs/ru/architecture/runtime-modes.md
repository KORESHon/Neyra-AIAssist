# Режимы рантайма

## `python main.py` (core)
- Запускает Internal API (`/v1`), WebSocket и веб-интерфейс.
- Создаёт один `NeyraAgent`.
- Поднимает resident-плагины в daemon thread.

## `python main.py --mode console`
- Терминальный чат для отладки промптов.
- Без HTTP-стека и без веб-панели.

## Resident vs on_demand
- `resident`: плагин стартует при запуске ядра.
- `on_demand`: плагин вызывается через API/инструменты по требованию.
