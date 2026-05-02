<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Архитектура Neyra

Neyra состоит из стабильного ядра и плагинов в `interfaces/`.

## Слои
- `core/`: агент, память, рефлексия, event bus, health monitor.
- `interfaces/internal_api/`: HTTP API + WebSocket + статическая раздача SPA (`frontend/dist`, React + Vite + Tailwind).
- `interfaces/discord/`: единый resident-плагин Discord (текст + музыка через Lavalink 4.x, события `MUSIC_*` на шине).
- `interfaces/*`: прочие расширения через Plugin SDK.

Опционально для IDE: MCP debug-сервер в `tools/mcp_server/` (логи, вызовы `/v1`, инъекция событий) — см. `docs/en/setup/mcp-debug-server.md`.

## Поток данных
1. `main.py` загружает `config.yaml`.
2. `core/plugin_config.py` подмешивает `interfaces/<id>/config.yaml`.
3. `core/secrets_loader.py` подставляет секреты из `.env`.
4. `core/server.py` запускает FastAPI и resident-плагины.
5. UI и внешние клиенты работают через `/v1` и `/v1/ws/*`.

## Принципы
- Вкл/выкл плагина: только `plugin.yaml`.
- Настройки плагина: `interfaces/<id>/config.yaml`.
- Секреты: только `.env`.