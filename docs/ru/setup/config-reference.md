<!-- co-authored-cursor-badge -->
[![Cursor AI assist](https://img.shields.io/badge/Cursor-AI_assist-141414?style=flat-square)](https://cursor.com)

<sub>Соавторство: материал создан при поддержке ИИ-агента [Cursor](https://cursor.com) (AI coding agent).</sub>

---

# Справочник config.yaml

`config.yaml` содержит только базовый runtime-конфиг ядра.

## Ключевые секции
- `assistant` — `name`, `persona_path` / `appearance_path` (этап 2A), `system_prompt` как fallback
- `BACKEND`, `openrouter`, `llm` — модели и лимиты по ролям: вложенные **`talk_model`**, **`brain_model`**, **`memory_model`**, **`vision_model`** (VL и пайплайн зрения в одном блоке; корневого **`vision:`** больше нет).
- `memory` — этап 2B `pre_context`; этап 2C `session_archive` (архив STM при overflow/reset; выкл. по умолчанию)
- `voice` — по модальностям: `stt` / `tts` с `prefer` + `local`/`cloud`.`enable` (soft ERROR если не настроено; legacy `voice_cloud` / `is_local` ещё нормализуются)
- `health_monitor`
- `backup`, `external_storage`
- `logging`

## Вынесено в плагины
- `discord` -> `interfaces/discord/config.yaml`
- `internal_api`, `dashboard` -> `interfaces/internal_api/config.yaml`
- локальные plugin settings -> `interfaces/<id>/config.yaml`

## Запрещено хранить в yaml
- API keys и токены. Используйте `.env`.