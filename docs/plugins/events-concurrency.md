# События и конкурентность

- Для обмена событиями используйте `core/event_bus.py`.
- Долгие операции выносите в `asyncio.to_thread`/отдельный процесс.
- Resident plugins не должны блокировать event loop API.
- Для внешних вызовов всегда ставьте timeout и retry policy.
