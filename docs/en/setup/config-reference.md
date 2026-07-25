<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Справочник config.yaml

`config.yaml` содержит только базовый runtime-конфиг ядра.

## Key sections
- `assistant`
- `BACKEND`, `openrouter`, `llm` — per-role nested blocks: **`talk_model`**, **`brain_model`**, **`memory_model`**, **`vision_model`** (VL + vision pipeline; no top-level **`vision:`**).
- `memory`
- `voice` — unified (`is_local` / `local` / `cloud` for STT+TTS; legacy `voice_cloud` removed from example)
- `health_monitor`
- `backup`, `external_storage`
- `logging`

## Вынесено в плагины
- `discord` -> `interfaces/discord/config.yaml`
- `internal_api`, `dashboard` -> `interfaces/internal_api/config.yaml`
- локальные plugin settings -> `interfaces/<id>/config.yaml`

## Запрещено хранить в yaml
- API keys и токены. Используйте `.env`.