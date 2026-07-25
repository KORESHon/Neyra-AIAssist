"""
core.neyra — главный оркестратор агента Нейры (единственный top-level модуль в core/).

Использует LangChain + OpenAI-compatible LLM.
Подсистемы: STM / Hub memory / PeopleDB / Tools / Event Bus.
Хелперы — пакет ``core.agent`` (фаза 1R).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import core.agent.micro_plan as _micro_plan
from core.agent.reply_postprocess import (
    EMPTY_REPLY_PLACEHOLDER,
    ensure_nonempty_reply,
    extract_sound_tags,
    extract_think_blocks,
)
from core.runtime.event_bus import EventBus
from core.runtime.identity import UnifiedIdentityMapper

logger = logging.getLogger("neyra.agent")

from core.agent.llm_setup import DEPRECATED_OPENROUTER_MODELS

# Маркер скрытого суффикса Discord GET_LYRICS — включает сохранение переносов строк и больший max_tokens.
LYRICS_REQUEST_MARKER = "[SYSTEM HIDDEN INSTRUCTION: User wants lyrics"


class NeyraAgent:
    """Основной агент Нейры.

    This class orchestrates LLM calls, memory subsystems, tools, and event
    publishing for all runtime interfaces (console, API, Discord plugin).

    Args:
        config: Merged runtime configuration dictionary.
    """

    def __init__(self, config: dict):
        self.config = config
        # Legacy MODE больше не основной; оставляем для обратной совместимости.
        self.mode = str(config.get("MODE") or config.get("BACKEND", "openrouter")).lower()
        # Ключ: discord channel_id → текст заметки после последнего VL-хода (пока процесс жив)
        self._last_vision_note_by_channel: dict[str, str] = {}

        self.event_bus = EventBus()
        self.identity = UnifiedIdentityMapper()

        self._setup_llm()
        self._setup_memory()
        self._setup_tools()
        self._setup_logs()
        self._project_root = Path(__file__).resolve().parents[1]
        self._wm_turns_since_refresh = 0
        self._wm_last_refresh_mono = 0.0
        self._emotion_last_mono = 0.0
        logger.info(f"NeyraAgent инициализирован | mode={self.mode}")

    # ─── Инициализация ─────────────────────────────────────────────────────

    def _setup_llm(self):
        """OpenAI-compatible LLM (OpenRouter, Ollama, Groq, …) — см. core.llm.profile."""
        from core.agent.llm_setup import setup_llm_connection

        setup_llm_connection(self)

    def _setup_openai_compatible_llm(self):
        """Единый путь: ChatOpenAI к base_url с api_key из профиля провайдера."""
        from core.agent.llm_setup import setup_openai_compatible_llm

        setup_openai_compatible_llm(self)

    def _vision_pipeline_cfg(self) -> dict[str, Any]:
        """Единый контур vision: openrouter.vision_model (см. core.llm.profile.merged_vision_pipeline)."""
        from core.llm.profile import merged_vision_pipeline

        return merged_vision_pipeline(self.config)

    def _uses_brain_native_vision(self) -> bool:
        return bool(self._vision_pipeline_cfg().get("use_brain_model_for_vision"))

    def _setup_memory(self):
        """Инициализирует все модули памяти."""
        from core.agent.bootstrap import setup_memory

        setup_memory(self)


    async def _append_turn_to_chat_log(
        self,
        *,
        user_text: str,
        assistant_text: str,
        internal_user_id: str,
        display_name: Optional[str],
        channel_id: Optional[str],
        source: Optional[str],
        meta: Optional[dict] = None,
        latency_ms: Optional[float] = None,
    ) -> str:
        """Dual-write full turn into SQLite chat_log (Memory Hub). Returns turn_id."""
        from core.agent.chat_log import append_turn_to_chat_log

        asst_cfg = self.config.get("assistant") if isinstance(self.config.get("assistant"), dict) else {}
        assistant_name = str(asst_cfg.get("name") or "").strip() or None
        return await append_turn_to_chat_log(
            self.memory_hub,
            user_text=user_text,
            assistant_text=assistant_text,
            internal_user_id=internal_user_id,
            display_name=display_name,
            channel_id=channel_id,
            source=source,
            assistant_name=assistant_name,
            meta=meta,
            latency_ms=latency_ms,
        )

    def _setup_tools(self):
        """Инициализирует инструменты (вызываются вручную, не через bind_tools)."""
        from core.agent.bootstrap import setup_tools

        setup_tools(self)


    async def start_mcp_clients(self) -> None:
        """Подключить MCP-серверы и добавить динамические tools (идемпотентно)."""
        await self._ensure_mcp()

    async def stop_mcp_clients(self) -> None:
        from core.agent.bootstrap import stop_mcp

        await stop_mcp(self)


    async def _ensure_mcp(self) -> None:
        from core.agent.bootstrap import ensure_mcp

        await ensure_mcp(self)


    def _setup_logs(self):
        """Создаёт директории и файлы для логов."""
        from core.agent.bootstrap import setup_logs

        setup_logs(self)


    def _init_people_db(self):
        """Засеивает базовые досье, только если Hub/PeopleDB ещё пусты (никакого JSON-импорта)."""
        from core.agent.people_seed import seed_default_people

        seed_default_people(self.people_db, getattr(self, "memory_hub", None))

    # ─── Системный промпт ──────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        extra_memories: list[str] = None,
        people_context_active: str = "",
        people_context_mentioned: str = "",
        diary_context: str = "",
        username: str = None,
        web_context: str = "",
        tool_context: str = "",
        has_vision_images: bool = False,
        last_image_context: Optional[str] = None,
        lyrics_mode: bool = False,
        mcp_tools_catalog: str = "",
        brain_router_context: str = "",
        attached_image_caption: str = "",
        working_memory_context: str = "",
    ) -> str:
        """Собирает системный промпт. Порядок (B2): роль → активный → упомянутые → правила → RAG → остальное."""
        from core.agent.prompts import build_talk_system_prompt

        return build_talk_system_prompt(
            base_prompt=self.config["assistant"]["system_prompt"],
            backend=self.backend,
            micro_plan=self._micro_plan_settings(),
            extra_memories=extra_memories,
            people_context_active=people_context_active,
            people_context_mentioned=people_context_mentioned,
            diary_context=diary_context,
            username=username,
            web_context=web_context,
            tool_context=tool_context,
            has_vision_images=has_vision_images,
            last_image_context=last_image_context,
            lyrics_mode=lyrics_mode,
            mcp_tools_catalog=mcp_tools_catalog,
            brain_router_context=brain_router_context,
            attached_image_caption=attached_image_caption,
            working_memory_context=working_memory_context,
        )

    def _build_brain_system_prompt(
        self,
        *,
        extra_memories: Optional[list[str]] = None,
        people_context_active: str = "",
        people_context_mentioned: str = "",
        diary_context: str = "",
        username: Optional[str] = None,
        web_context: str = "",
        tool_context: str = "",
        mcp_tools_catalog: str = "",
        last_image_context: Optional[str] = None,
        working_memory_context: str = "",
    ) -> str:
        """Компактный системный промпт для brain: инструменты и факты, без личности talk-модели."""
        from core.agent.prompts import build_brain_system_prompt

        return build_brain_system_prompt(
            extra_memories=extra_memories,
            people_context_active=people_context_active,
            people_context_mentioned=people_context_mentioned,
            diary_context=diary_context,
            username=username,
            web_context=web_context,
            tool_context=tool_context,
            mcp_tools_catalog=mcp_tools_catalog,
            last_image_context=last_image_context,
            working_memory_context=working_memory_context,
        )

    async def _caption_vision_images(
        self,
        user_message: str,
        vision_images: list[tuple[str, str]],
        *,
        speaker_label: str,
    ) -> str:
        """Краткий текстовый конспект изображений через VL-модель (до brain/talk)."""
        from langchain_core.messages import HumanMessage, SystemMessage

        if not vision_images or not self.llm_vision:
            return ""
        sys = SystemMessage(
            content=(
                "Ты модуль зрения. Кратко по-русски опиши, что на изображении (1–8 предложений). "
                "Несколько картинок — перечисли по порядку. Текст на экране — по возможности дословно. "
                "Без личности ассистента, без markdown-заголовков."
            )
        )
        human = self._make_human_turn(
            (user_message or "").strip() or "Что на изображении?",
            vision_images,
            speaker_label=speaker_label,
        )
        resp = await self.llm_vision.ainvoke([sys, human])
        raw = resp.content if hasattr(resp, "content") else str(resp)
        caption = (raw or "").strip()
        self._log_model_route(self._extract_model_name(resp), lane="vision")
        return caption

    async def _run_brain_tool_phase(
        self,
        *,
        user_message: str,
        speaker_label: str,
        vision_caption: Optional[str],
        vision_images: Optional[list[tuple[str, str]]] = None,
        brain_system: str,
        lyrics_mode: bool,
    ) -> str:
        """Маршрутизация и tool-loop на llm_brain; возвращает текст для секции talk «brain»."""
        from core.agent.brain_phase import run_brain_tool_phase

        return await run_brain_tool_phase(
            self,
            user_message=user_message,
            speaker_label=speaker_label,
            vision_caption=vision_caption,
            vision_images=vision_images,
            brain_system=brain_system,
            lyrics_mode=lyrics_mode,
        )

    def _make_vision_memory_note(self, thoughts: str, clean_text: str) -> str:
        """Текст для «памяти последнего скрина»: приоритет — CoT/think из ответа VL."""
        from core.agent.vision_context import make_vision_memory_note

        vis = self._vision_pipeline_cfg()
        return make_vision_memory_note(
            thoughts,
            clean_text,
            max_chars=int(vis.get("last_image_note_max_chars", 1200)),
        )

    def _last_image_context_for_prompt(
        self,
        channel_id: Optional[str],
        vision_images: Optional[list],
    ) -> Optional[str]:
        from core.agent.vision_context import last_image_context_for_prompt

        vis_cfg = self._vision_pipeline_cfg()
        return last_image_context_for_prompt(
            self._last_vision_note_by_channel,
            channel_id,
            vision_images,
            remember_last_image=bool(vis_cfg.get("remember_last_image", True)),
        )

    def _store_vision_note_if_needed(
        self,
        channel_id: Optional[str],
        vision_images: Optional[list],
        thoughts: str,
        clean_text: str,
    ) -> None:
        from core.agent.vision_context import store_vision_note_if_needed

        vis = self._vision_pipeline_cfg()
        store_vision_note_if_needed(
            self._last_vision_note_by_channel,
            channel_id,
            vision_images,
            thoughts,
            clean_text,
            remember_last_image=bool(vis.get("remember_last_image", True)),
            max_chars=int(vis.get("last_image_note_max_chars", 1200)),
        )

    def _resolve_speaker_label(
        self,
        username: Optional[str],
        discord_user_id: Optional[str],
        author_display_name: Optional[str] = None,
    ) -> str:
        """Подпись собеседника для STM, HumanMessage и system prompt (этап B1)."""
        from core.agent.speakers import resolve_speaker_label

        return resolve_speaker_label(
            self.memory_hub, username, discord_user_id, author_display_name
        )

    def _format_spoken_user_message(self, text: str, speaker_label: str) -> str:
        """Префикс авторства реплики в контексте LLM ([Пользователь …]: …)."""
        from core.agent.speakers import format_spoken_user_message

        return format_spoken_user_message(text, speaker_label)

    def _make_human_turn(
        self,
        user_message: str,
        vision_images: Optional[list[tuple[str, str]]] = None,
        *,
        speaker_label: Optional[str] = None,
    ):
        """HumanMessage: текст или мультимодальный контент (mime, base64) для VL."""
        from core.agent.speakers import make_human_turn

        return make_human_turn(
            user_message,
            vision_images,
            speaker_label=speaker_label,
            has_vision_llm=self.llm_vision is not None,
        )

    def _stream_llm(self, vision_images: Optional[list[tuple[str, str]]]):
        """Какой LLM вызывать в этом ходе."""
        if vision_images and self.llm_vision:
            return self.llm_vision
        return self.llm

    def _extract_model_name(self, payload: Any) -> Optional[str]:
        from core.agent.llm_stream import extract_model_name

        return extract_model_name(payload)

    def _log_model_route(self, used_model: Optional[str], *, lane: str = "talk") -> None:
        from core.agent.llm_stream import log_model_route

        log_model_route(self, used_model, lane=lane)


    async def _run_async_reflection(
        self,
        user_message: str,
        assistant_text: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        from core.agent.memory_jobs import run_async_reflection

        await run_async_reflection(
            self, user_message, assistant_text, username, discord_user_id
        )

    def _schedule_async_reflection(
        self,
        user_message: str,
        assistant_text: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        from core.agent.memory_jobs import schedule_async_reflection

        schedule_async_reflection(
            self, user_message, assistant_text, username, discord_user_id
        )

    def _format_stm_tail(self, max_messages: int = 12) -> str:
        from core.agent.memory_jobs import format_stm_tail

        return format_stm_tail(self.short_memory, max_messages)

    def _read_working_memory_for_prompt(self, internal_user_id: str) -> str:
        return self.memory_hub.working_memory_for_prompt(
            internal_user_id, root=self._project_root
        )

    async def _run_working_memory_refresh(
        self,
        *,
        internal_user_id: str,
        user_message: str,
        assistant_text: str,
        speaker_label: str,
        reason: str,
    ) -> None:
        from core.agent.memory_jobs import run_working_memory_refresh

        await run_working_memory_refresh(
            self,
            internal_user_id=internal_user_id,
            user_message=user_message,
            assistant_text=assistant_text,
            speaker_label=speaker_label,
            reason=reason,
        )

    def _schedule_working_memory_refresh(
        self,
        *,
        internal_user_id: str,
        user_message: str,
        assistant_text: str,
        speaker_label: str,
        stm_trimmed: bool = False,
    ) -> None:
        from core.agent.memory_jobs import schedule_working_memory_refresh

        schedule_working_memory_refresh(
            self,
            internal_user_id=internal_user_id,
            user_message=user_message,
            assistant_text=assistant_text,
            speaker_label=speaker_label,
            stm_trimmed=stm_trimmed,
        )

    async def _save_dialog_to_ltm_with_emotion(
        self,
        user_message: str,
        clean_text: str,
        metadata: dict,
        speaker_label: str,
    ) -> None:
        from core.agent.memory_jobs import save_dialog_to_ltm_with_emotion

        await save_dialog_to_ltm_with_emotion(
            self, user_message, clean_text, metadata, speaker_label
        )

    def _schedule_emotion_diary(
        self,
        *,
        user_message: str,
        assistant_text: str,
        speaker_label: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        from core.agent.memory_jobs import schedule_emotion_diary

        schedule_emotion_diary(
            self,
            user_message=user_message,
            assistant_text=assistant_text,
            speaker_label=speaker_label,
            username=username,
            discord_user_id=discord_user_id,
        )

    async def _ainvoke_text_with_fallback(self, messages: list[Any], *, llm=None):
        """Обычный нестриминговый вызов (одна модель)."""
        model = llm or self.llm_talk
        return await model.ainvoke(messages)

    async def _astream_text_with_fallback(self, messages: list[Any], *, llm=None):
        """Стриминговый вызов live-модели с guard по first-token timeout и 1 ретраем."""
        from core.agent.llm_stream import astream_text_with_fallback

        async for chunk in astream_text_with_fallback(self, messages, llm=llm):
            yield chunk


    # ─── Вспомогательные методы ────────────────────────────────────────────

    def _micro_plan_settings(self) -> _micro_plan.MicroPlanSettings:
        return _micro_plan.MicroPlanSettings(
            enabled=bool(self.micro_planning_enabled),
            mode=str(self.micro_plan_mode),
            start=str(self.micro_plan_start),
            end=str(self.micro_plan_end),
            anchor_prefix=str(self.micro_plan_anchor_prefix),
            anchor_reply=str(self.micro_plan_anchor_reply),
            prefill_enabled=bool(self.micro_plan_prefill_enabled),
        )

    def _extract_sound_tags(self, text: str, *, preserve_line_breaks: bool = False) -> tuple[str, list[str]]:
        """Вырезает [SOUND: tag] из текста, возвращает (чистый текст, список тегов)."""
        return extract_sound_tags(text, preserve_line_breaks=preserve_line_breaks)

    def _extract_think_blocks(self, text: str) -> tuple[str, str]:
        """Вырезает <think>/<thought> блоки (модель использует оба варианта)."""
        return extract_think_blocks(text)

    def _ensure_nonempty_reply(
        self,
        text_no_think: str,
        clean_text: str,
        *,
        preserve_line_breaks: bool = False,
    ) -> str:
        """
        Гарантирует, что после пост-очистки ответ не станет пустым.
        Иногда модель уходит в служебные блоки/скобки и после фильтров ничего не остаётся.
        """
        return ensure_nonempty_reply(
            text_no_think,
            clean_text,
            preserve_line_breaks=preserve_line_breaks,
            empty_placeholder=EMPTY_REPLY_PLACEHOLDER,
        )

    async def _retry_short_reply_if_empty(self, messages: list[Any], current_text: str) -> str:
        """Если после очистки ответ пустой, делаем быстрый короткий re-ask одной фразой."""
        if (current_text or "").strip() != EMPTY_REPLY_PLACEHOLDER:
            return current_text
        try:
            from langchain_core.messages import SystemMessage
            guard = SystemMessage(
                content=(
                    "Срочный повтор: ответь ОДНОЙ короткой фразой по-русски (до 18 слов), "
                    "без тегов, скобок и внутреннего мышления."
                )
            )
            retry_messages = [messages[0], guard, *messages[1:]] if messages else [guard]
            resp = await self.llm_talk.ainvoke(retry_messages)
            raw = resp.content if hasattr(resp, "content") else str(resp)
            text_no_think, _ = self._extract_think_blocks(raw)
            clean, _ = self._extract_sound_tags(text_no_think)
            clean = (clean or "").strip()
            if clean:
                logger.info("Пустой ответ восстановлен через short re-ask")
                return clean
        except Exception as e:
            logger.warning("Short re-ask ошибка: %s", e)
        return current_text

    def _strip_leading_micro_plan(self, text: str) -> tuple[str, str]:
        """Удаляет ведущий [PLAN]...[/PLAN] (или кастомные теги) из ответа."""
        return _micro_plan.strip_leading(text, self._micro_plan_settings())

    def _init_micro_plan_state(self) -> dict:
        return _micro_plan.init_state()

    def _filter_micro_plan_token(self, token: str, st: dict) -> str:
        """State-machine фильтр: скрывает содержимое между start/end тегами без буферизации всего ответа."""
        return _micro_plan.filter_token(token, st, self._micro_plan_settings())

    def _filter_micro_plan_token_anchor(self, token: str, st: dict) -> str:
        return _micro_plan.filter_token_anchor(token, st, self._micro_plan_settings())

    def _finalize_micro_plan_state(self, st: dict) -> str:
        return _micro_plan.finalize_state(st, self._micro_plan_settings(), self._micro_plan_metrics)

    def _strip_micro_plan_blocks(self, text: str) -> tuple[str, int, bool]:
        """Финальный fail-safe: вырезает все блоки start...end и обрезает незакрытый хвост."""
        return _micro_plan.strip_blocks(text, self._micro_plan_settings())

    def _strip_micro_plan_anchor(self, text: str) -> tuple[str, int, bool]:
        return _micro_plan.strip_anchor(text, self._micro_plan_settings())

    def _maybe_append_micro_plan_prefill(
        self,
        messages: list[Any],
        *,
        has_vision_images: bool,
    ) -> list[Any]:
        return _micro_plan.maybe_append_prefill(
            messages,
            self._micro_plan_settings(),
            has_vision_images=has_vision_images,
        )

    async def _de_repeat_reply(self, user_message: str, clean_text: str) -> str:
        """Если новый ответ почти дублирует предыдущий — быстрый перефраз."""
        from core.agent.de_repeat import de_repeat_reply

        return await de_repeat_reply(
            user_message=user_message,
            clean_text=clean_text,
            short_memory=self.short_memory,
            llm_talk=self.llm_talk,
            lyrics_marker=LYRICS_REQUEST_MARKER,
            extract_think_blocks=self._extract_think_blocks,
            extract_sound_tags=self._extract_sound_tags,
        )

    def _log_thought(self, thought: str, user_msg: str):
        """Пишет внутренний монолог в thoughts.log."""
        if not thought:
            return
        with open(self.thoughts_log_path, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().isoformat()}] Запрос: {user_msg[:80]}\n")
            f.write(f"<think>\n{thought}\n</think>\n")

    def _log_chat(self, user: str, assistant: str, metadata: dict = None):
        """Пишет диалог в chat.log."""
        with open(self.chat_log_path, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            who = metadata.get("username", "User") if metadata else "User"
            f.write(f"\n[{ts}] {who}: {user}\n")
            f.write(f"[{ts}] Нейра: {assistant}\n")

    def _detect_mentioned_names(self, text: str) -> list[str]:
        """Определение известных имён/ников с учетом русских окончаний (падежей)."""
        from core.agent.people_context import detect_mentioned_names

        return detect_mentioned_names(text, self.memory_hub.get_all_names_map())

    def _split_people_context_for_prompt(
        self,
        mentioned: list[str],
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> tuple[str, str]:
        """
        B2: досье текущего пользователя отдельно от прочих упомянутых (без дублирования).
        """
        from core.agent.people_context import split_people_context

        return split_people_context(self.memory_hub, mentioned, username, discord_user_id)

    @staticmethod
    def _shrink_people_sections(active: str, mentioned: str, max_chars: int) -> tuple[str, str]:
        """Ужимает блоки досье при переполнении контекста; приоритет — активный собеседник."""
        from core.agent.people_context import shrink_people_sections

        return shrink_people_sections(active, mentioned, max_chars)

    # ─── Инструменты — ручной вызов ────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, **kwargs) -> str:
        """Выполняет инструмент по имени (встроенный или MCP)."""
        t = self.tools.get(tool_name)
        if not t:
            return f"Инструмент '{tool_name}' не найден"
        try:
            if hasattr(t, "ainvoke"):
                return str(await t.ainvoke(kwargs))
            return str(t.invoke(kwargs))
        except Exception as e:
            logger.error(f"Tool {tool_name} ошибка: {e}")
            return f"Ошибка инструмента: {e}"

    def _collect_tool_context(self, text: str) -> str:
        from core.agent.tool_heuristics import collect_tool_context

        return collect_tool_context(
            self.tools,
            text=text,
            rag_enabled=bool(self.long_memory.rag_enabled),
            detect_mentioned_names=self._detect_mentioned_names,
        )

    def _handle_memory_trigger(self, text: str, mentioned: list[str], username: str) -> list[str]:
        from core.agent.tool_heuristics import handle_memory_trigger

        return handle_memory_trigger(
            people_db=self.people_db,
            memory_hub=self.memory_hub,
            text=text,
            mentioned=mentioned,
            username=username,
        )

    def add_diary_entry(self, text: str, source: str = "manual", meta: Optional[dict] = None) -> bool:
        """Ручная запись в личный дневник Нейры."""
        return self.diary.add_entry(text=text, source=source, meta=meta)

    def get_recent_diary(self, limit: int = 12) -> str:
        return self.memory_hub.diary_recent_text(limit=limit) or "Дневник пока пуст."

    def _handle_websearch_trigger(self, text: str) -> str:
        from core.agent.tool_heuristics import handle_websearch_trigger

        return handle_websearch_trigger(self.tools, text)

    def _resolve_internal_user_id(
        self, discord_user_id: Optional[str], username: Optional[str]
    ) -> str:
        rid = self.identity.resolve_from_discord(discord_user_id)
        if rid:
            return rid
        return self.identity.resolve_console(username)

    def _publish_memory_and_chat_events(
        self,
        *,
        internal_user_id: str,
        channel_id: Optional[str],
        username: Optional[str],
        user_message: str,
        clean_text: str,
        sounds: list,
        metadata: dict,
    ) -> None:
        from core.agent.turn_events import publish_memory_and_chat_events

        publish_memory_and_chat_events(
            self.event_bus,
            internal_user_id=internal_user_id,
            channel_id=channel_id,
            username=username,
            user_message=user_message,
            clean_text=clean_text,
            sounds=sounds,
            metadata=metadata,
            short_memory_len=len(self.short_memory),
            rag_enabled=self.long_memory.rag_enabled,
        )

    def _publish_chat_turn_failed(
        self,
        *,
        internal_user_id: str,
        channel_id: Optional[str],
        error: str,
    ) -> None:
        from core.agent.turn_events import publish_chat_turn_failed

        publish_chat_turn_failed(
            self.event_bus,
            internal_user_id=internal_user_id,
            channel_id=channel_id,
            error=error,
        )

    async def chat(
        self,
        user_message: str,
        username: Optional[str] = None,
        discord_user_id: Optional[str] = None,
        vision_images: Optional[list[tuple[str, str]]] = None,
        channel_id: Optional[str] = None,
        author_display_name: Optional[str] = None,
    ) -> dict:
        """
        Основной метод чата.

        Возвращает:
        {
            "text": str,          — финальный текст ответа (без тегов и think)
            "sounds": list[str],  — список звуковых тегов [SOUND: laugh] → ["laugh"]
            "thoughts": str,      — внутренний монолог (для лога, не показываем)
            "raw": str,           — полный сырой ответ модели
        }
        """
        from core.agent.reply_pipeline import (
            log_micro_plan_metrics,
            polish_clean_reply,
            sanitize_raw_reply,
        )
        from core.agent.talk_messages import build_talk_messages, build_talk_system_prompt
        from core.agent.turn_finalize import finalize_successful_turn
        from core.agent.turn_prep import prepare_turn

        prep = await prepare_turn(
            self,
            user_message=user_message,
            username=username,
            discord_user_id=discord_user_id,
            vision_images=vision_images,
            channel_id=channel_id,
            author_display_name=author_display_name,
            lyrics_marker=LYRICS_REQUEST_MARKER,
            log_lane="chat",
        )
        caption_ok = (prep.attached_caption or "").strip()
        brain_context = ""
        try:
            brain_context = await self._run_brain_tool_phase(
                user_message=user_message,
                speaker_label=prep.speaker_label,
                vision_caption=caption_ok or None,
                vision_images=vision_images if prep.brain_native_vis else None,
                brain_system=prep.brain_sys,
                lyrics_mode=prep.lyrics_mode,
            )
        except Exception as e:
            logger.warning("Brain phase: пропуск сводки — %s", e)

        system_prompt = build_talk_system_prompt(self, prep, brain_context=brain_context)
        messages = build_talk_messages(
            self, prep, system_prompt, user_message=user_message, vision_images=vision_images
        )
        final_messages_used = messages

        try:
            cap_llm = (
                self.llm_talk.bind(max_tokens=max(self.reply_max_tokens, self.lyrics_reply_max_tokens))
                if prep.lyrics_mode
                else self.llm_talk
            )
            response = await self._ainvoke_text_with_fallback(messages, llm=cap_llm)
            self._log_model_route(self._extract_model_name(response), lane="talk")
            raw_response = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error("Ошибка вызова LLM: %s", e)
            self._publish_chat_turn_failed(
                internal_user_id=prep.internal_uid,
                channel_id=channel_id,
                error=str(e),
            )
            return {
                "text": f"[SOUND: bruh] Что-то сломалось на моей стороне: {e}",
                "sounds": ["bruh"],
                "thoughts": "",
                "raw": "",
            }

        clean_text, thoughts, sounds = sanitize_raw_reply(
            self, raw_response, lyrics_mode=prep.lyrics_mode, mode_label="chat"
        )
        clean_text = await polish_clean_reply(
            self,
            user_message=user_message,
            clean_text=clean_text,
            messages=final_messages_used,
        )

        await finalize_successful_turn(
            self,
            user_message=user_message,
            clean_text=clean_text,
            thoughts=thoughts,
            sounds=sounds,
            username=username,
            discord_user_id=discord_user_id,
            channel_id=channel_id,
            speaker_label=prep.speaker_label,
            internal_uid=prep.internal_uid,
            vision_images=vision_images,
            saved_facts=prep.saved_facts,
            source="chat",
            stm_trimmed=False,
        )
        log_micro_plan_metrics(self)
        return {
            "text": clean_text,
            "sounds": sounds,
            "thoughts": thoughts,
            "raw": raw_response,
        }

    async def chat_stream(
        self,
        user_message: str,
        username: Optional[str] = None,
        discord_user_id: Optional[str] = None,
        vision_images: Optional[list[tuple[str, str]]] = None,
        channel_id: Optional[str] = None,
        author_display_name: Optional[str] = None,
    ):
        """
        Стриминговый чат — yield'ит токены сразу как модель их генерирует.

        Использование:
            async for chunk in agent.chat_stream(msg):
                if chunk["type"] == "token":
                    print(chunk["text"], end="", flush=True)
                elif chunk["type"] == "done":
                    sounds = chunk["sounds"]
        """
        from core.agent.reply_pipeline import (
            log_micro_plan_metrics,
            polish_clean_reply,
            sanitize_raw_reply,
        )
        from core.agent.talk_messages import build_talk_messages, build_talk_system_prompt
        from core.agent.turn_finalize import finalize_successful_turn
        from core.agent.turn_prep import prepare_turn

        prep = await prepare_turn(
            self,
            user_message=user_message,
            username=username,
            discord_user_id=discord_user_id,
            vision_images=vision_images,
            channel_id=channel_id,
            author_display_name=author_display_name,
            lyrics_marker=LYRICS_REQUEST_MARKER,
            log_lane="stream",
        )
        caption_ok = (prep.attached_caption or "").strip()
        brain_context = ""
        try:
            brain_context = await self._run_brain_tool_phase(
                user_message=user_message,
                speaker_label=prep.speaker_label,
                vision_caption=caption_ok or None,
                vision_images=vision_images if prep.brain_native_vis else None,
                brain_system=prep.brain_sys,
                lyrics_mode=prep.lyrics_mode,
            )
        except Exception as e:
            logger.warning("Brain phase (stream): пропуск сводки — %s", e)

        system_prompt = build_talk_system_prompt(self, prep, brain_context=brain_context)
        stream_llm = self.llm_talk
        if prep.lyrics_mode:
            stream_llm = self.llm_talk.bind(
                max_tokens=max(self.reply_max_tokens, self.lyrics_reply_max_tokens)
            )
        if vision_images:
            mode = "brain-native" if prep.brain_native_vis else "caption→brain→talk"
            logger.info(
                "Зрение: %s, изображений=%s | talk_model=%s",
                mode,
                len(vision_images),
                getattr(self, "llm_talk_model", self.llm_model),
            )

        messages = build_talk_messages(
            self, prep, system_prompt, user_message=user_message, vision_images=vision_images
        )
        final_messages_used = messages

        # 3. Стриминг — yield токены по мере генерации
        raw_response = ""
        context_exceeded = False
        used_model_name: Optional[str] = None
        plan_state = self._init_micro_plan_state()
        raw_chunk_count = 0
        yielded_chunk_count = 0
        try:
            stream_iter = self._astream_text_with_fallback(messages, llm=stream_llm)
            async for chunk in stream_iter:
                if used_model_name is None:
                    used_model_name = self._extract_model_name(chunk)
                token = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token:
                    raw_chunk_count += 1
                    raw_response += token
                    visible = self._filter_micro_plan_token(token, plan_state)
                    if visible:
                        yield {"type": "token", "text": visible}
                        yielded_chunk_count += 1
            tail = self._finalize_micro_plan_state(plan_state)
            if tail:
                yield {"type": "token", "text": tail}
                yielded_chunk_count += 1
            self._log_model_route(used_model_name, lane="talk")
            logger.debug(
                "LLM stream stats | raw_chunks=%s | yielded_chunks=%s | micro_plan=%s",
                raw_chunk_count,
                yielded_chunk_count,
                self.micro_planning_enabled,
            )

        except Exception as e:
            err_str = str(e)

            # Контекст переполнен → чистим память и пробуем снова
            if "context size has been exceeded" in err_str.lower() or "context_length_exceeded" in err_str.lower():
                context_exceeded = True
                logger.warning(f"Контекст переполнен (LMStudio n_ctx мал)! Очищаю историю до 1 сообщения и урезаю промпт...")
                # Очищаем историю почти в ноль
                self.short_memory.trim_to_half()
                self.short_memory.trim_to_half()
                
                # Урезаем системный промпт (убираем веб и память, оставляем только базу)
                system_prompt = build_talk_system_prompt(
                    self, prep, brain_context=brain_context,
                    shrink_people=True, drop_extra_context=True,
                )
                messages_retry = build_talk_messages(
                    self, prep, system_prompt,
                    user_message=user_message, vision_images=vision_images,
                )
                final_messages_used = messages_retry

                try:
                    retry_iter = self._astream_text_with_fallback(messages_retry, llm=stream_llm)
                    async for chunk in retry_iter:
                        if used_model_name is None:
                            used_model_name = self._extract_model_name(chunk)
                        token = chunk.content if hasattr(chunk, "content") else str(chunk)
                        if token:
                            raw_chunk_count += 1
                            raw_response += token
                            visible = self._filter_micro_plan_token(token, plan_state)
                            if visible:
                                yield {"type": "token", "text": visible}
                                yielded_chunk_count += 1
                    tail = self._finalize_micro_plan_state(plan_state)
                    if tail:
                        yield {"type": "token", "text": tail}
                        yielded_chunk_count += 1
                    self._log_model_route(used_model_name, lane="talk")
                    logger.debug(
                        "LLM stream stats | raw_chunks=%s | yielded_chunks=%s | micro_plan=%s | retry=true",
                        raw_chunk_count,
                        yielded_chunk_count,
                        self.micro_planning_enabled,
                    )
                except Exception as e2:
                    logger.error(f"Ошибка повторного запроса (даже с урезанным контекстом): {e2}")
                    self._publish_chat_turn_failed(
                        internal_user_id=prep.internal_uid,
                        channel_id=channel_id,
                        error=str(e2),
                    )
                    yield {"type": "error", "text": str(e2)}
                    return
            else:
                logger.error(f"Ошибка стриминга LLM: {e}")
                self._publish_chat_turn_failed(
                    internal_user_id=prep.internal_uid,
                    channel_id=channel_id,
                    error=err_str,
                )
                yield {"type": "error", "text": err_str}
                return

        # 4. Постобработка после завершения стрима
        clean_text, thoughts, sounds = sanitize_raw_reply(
            self, raw_response, lyrics_mode=prep.lyrics_mode, mode_label="stream"
        )
        clean_text = await polish_clean_reply(
            self,
            user_message=user_message,
            clean_text=clean_text,
            messages=final_messages_used,
        )

        if context_exceeded:
            logger.info("Успешный ответ после переполнения контекста.")

        await finalize_successful_turn(
            self,
            user_message=user_message,
            clean_text=clean_text,
            thoughts=thoughts,
            sounds=sounds,
            username=username,
            discord_user_id=discord_user_id,
            channel_id=channel_id,
            speaker_label=prep.speaker_label,
            internal_uid=prep.internal_uid,
            vision_images=vision_images,
            saved_facts=prep.saved_facts,
            source="chat_stream",
            stm_trimmed=context_exceeded,
        )
        log_micro_plan_metrics(self)
        logger.debug("Стрим завершён | sounds=%s | len=%s", sounds, len(clean_text))

        yield {
            "type": "done",
            "text": clean_text,
            "sounds": sounds,
            "thoughts": thoughts,
            "raw": raw_response,
        }

    async def summarize_ltm_corpus(self, combined_dialog_text: str, *, consolidation: bool = False) -> str:
        """
        Сжимает пакет выгружаемых диалогов LTM в короткий digest для последующей записи в RAG.
        Использует reflection-модель с умеренным лимитом токенов (обслуживание памяти, не чат).
        consolidation=True — режим ночной консолидации: слияние дублей, отсечение шума.
        """
        from langchain_core.messages import HumanMessage

        raw = (combined_dialog_text or "").strip()
        if not raw:
            return ""
        cap = 120_000
        if len(raw) > cap:
            raw = raw[: cap - 100] + "\n… [truncated for summarization]"

        mem_cfg = self.config.get("memory") if isinstance(self.config.get("memory"), dict) else {}
        if self.reflection_max_tokens is not None:
            default_summarize = min(self.reflection_max_tokens * 2, 4096)
        else:
            default_summarize = 4096
        max_out = int(mem_cfg.get("ltm_summarize_max_tokens", default_summarize))
        if consolidation:
            prompt = (
                "Ниже — близкие по смыслу фрагменты долговременной памяти (один кластер). "
                "Объедини явные дубли и повторы одной мысли; убери шум и пустяки без потери фактов. "
                "Если темы разные — структурируй короткими подзаголовками (markdown ##). "
                "Только русский; не выдумывай факты; если мало сигнала — 2–4 предложения.\n\n---\n\n"
                f"{raw}"
            )
        else:
            prompt = (
                "Ниже — фрагменты старых диалогов из долговременной памяти. "
                "Сожми их в один связный markdown-текст на русском: темы, имена, факты, без воды и без выдумок. "
                "Если данных мало — дай 2–4 предложения.\n\n---\n\n"
                f"{raw}"
            )
        llm = getattr(self, "llm_memory", None) or getattr(self, "llm_reflection", None) or self.llm_talk
        from core.llm.retry import ainvoke_with_rate_limit_backoff

        call = llm.bind(max_tokens=max_out) if hasattr(llm, "bind") else llm
        resp = await ainvoke_with_rate_limit_backoff(
            call, [HumanMessage(content=prompt)], lane="memory_model"
        )
        text = getattr(resp, "content", None)
        return (str(text) if text is not None else "").strip()

    def reset_context(self, channel_id: Optional[str] = None):
        """Сбрасывает краткую память; для Discord — ещё заметку последнего скрина в этом канале."""
        self.short_memory.clear()
        if channel_id is not None:
            self._last_vision_note_by_channel.pop(str(channel_id), None)
        else:
            self._last_vision_note_by_channel.clear()
        logger.info("Краткосрочная память сброшена")

    def get_stats(self) -> dict:
        """Возвращает статистику агента."""
        mcp_info = None
        if self.mcp_manager is not None:
            mcp_info = {
                "configured_servers": len(self.mcp_manager.configured_servers()),
                "connected_servers": self.mcp_manager.connected_servers(),
                "errors": self.mcp_manager.last_errors(),
            }
        from core.memory import emotional_layer as em
        from core.memory import working_memory as wm

        return {
            "mode": self.mode,
            "llm_provider": self.backend,
            "model": self.llm_model,
            "talk_model": getattr(self, "llm_talk_model", self.llm_model),
            "brain_model": getattr(self, "llm_brain_model", None),
            "memory_model": getattr(self, "llm_memory_model", None),
            "short_memory_size": len(self.short_memory),
            "long_memory_records": self.long_memory.count(),
            "people_db_records": len(self.people_db._cache),
            "tools_count": len(self.tools),
            "event_bus": self.event_bus.handler_counts(),
            "mcp": mcp_info,
            "working_memory_enabled": wm.wm_enabled(self.config),
            "emotional_layer_enabled": em.layer_enabled(self.config),
        }
