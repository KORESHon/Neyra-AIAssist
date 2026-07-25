<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Справочник config.yaml

`config.yaml` содержит только базовый runtime-конфиг ядра.

## Key sections
- `assistant` — `name`, `persona_path` / `appearance_path` (Stage 2A), `system_prompt` fallback
- `BACKEND`, `openrouter`, `llm` — per-role nested blocks: **`talk_model`**, **`brain_model`**, **`memory_model`**, **`vision_model`** (VL + vision pipeline; no top-level **`vision:`**).
- `memory` — Stage 2B `pre_context`; Stage 2C `session_archive` (STM archive on overflow/reset; off by default)
- `voice` — per modality: `stt` / `tts` each with `prefer` + `local`/`cloud`.`enable` (soft ERROR if unset; legacy `voice_cloud` / `is_local` still normalized)
- `health_monitor`
- `backup`, `external_storage`
- `logging`

## Вынесено в плагины
- `discord` -> `interfaces/discord/config.yaml`
- `internal_api`, `dashboard` -> `interfaces/internal_api/config.yaml`
- локальные plugin settings -> `interfaces/<id>/config.yaml`

## Запрещено хранить в yaml
- API keys и токены. Используйте `.env`.