"""
core.agent.neyra — Главный агент Нейры (оркестрация).

Использует LangChain + OpenAI-compatible LLM.
Подсистемы: STM / Hub memory / PeopleDB / Tools / Event Bus.
Хелперы вынесены в core.agent.reply_postprocess и core.agent.micro_plan (фаза 1R).
"""

from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import micro_plan as _micro_plan
from .reply_postprocess import (
    EMPTY_REPLY_PLACEHOLDER,
    ensure_nonempty_reply,
    extract_sound_tags,
    extract_think_blocks,
)
from core.event_bus import EventBus
from core.identity import UnifiedIdentityMapper

logger = logging.getLogger("neyra.agent")

DEPRECATED_OPENROUTER_MODELS: dict[str, str] = {
    "openrouter/elephant-alpha": "inclusionai/ling-2.6-flash:free",
}

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
        self._project_root = Path(__file__).resolve().parents[2]
        self._wm_turns_since_refresh = 0
        self._wm_last_refresh_mono = 0.0
        self._emotion_last_mono = 0.0
        logger.info(f"NeyraAgent инициализирован | mode={self.mode}")

    # ─── Инициализация ─────────────────────────────────────────────────────

    def _setup_llm(self):
        """OpenAI-compatible LLM (OpenRouter, Ollama, Groq, …) — см. core.llm_profile."""
        from core.llm_profile import resolve_openai_compatible_connection

        self._llm_connection = resolve_openai_compatible_connection(self.config)
        self.backend = self._llm_connection.provider
        self._setup_openai_compatible_llm()

    def _setup_openai_compatible_llm(self):
        """Единый путь: ChatOpenAI к base_url с api_key из профиля провайдера."""
        from langchain_openai import ChatOpenAI

        from core.llm_profile import (
            merge_llm_tuning_options,
            resolved_brain_model,
            resolved_memory_model,
            resolved_talk_model,
            resolved_vision_model_id,
        )

        conn = self._llm_connection
        cfg = merge_llm_tuning_options(self.config)
        talk_model = resolved_talk_model(self.config, conn.provider)
        brain_model = resolved_brain_model(self.config, conn.provider)
        memory_model_raw = resolved_memory_model(self.config, conn.provider)
        memory_model = DEPRECATED_OPENROUTER_MODELS.get(memory_model_raw, memory_model_raw)
        if memory_model != memory_model_raw:
            logger.warning(
                "Memory model '%s' is deprecated, using '%s' instead.",
                memory_model_raw,
                memory_model,
            )
        vision_model_id = resolved_vision_model_id(self.config, conn.provider)
        self.context_window = cfg.get("context_window", 16384)
        base_url = conn.base_url
        api_key = conn.api_key
        self.reply_max_tokens = int(cfg.get("reply_max_tokens", cfg.get("max_tokens", 320)))
        self.vision_max_tokens = int(cfg.get("vision_max_tokens", cfg.get("max_tokens", 900)))
        _refl_cap = cfg.get("reflection_max_tokens")
        self.reflection_max_tokens = int(_refl_cap) if _refl_cap is not None else None
        # Длинные ответы (текст песни): отдельный потолок; bind() на конкретный ход в chat_stream/chat.
        self.lyrics_reply_max_tokens = int(cfg.get("lyrics_reply_max_tokens", 4096))
        self.reflection_temperature = float(cfg.get("reflection_temperature", cfg.get("temperature", 0.75)))
        _brain_cap = cfg.get("brain_max_tokens")
        self.brain_max_tokens = int(_brain_cap) if _brain_cap is not None else None
        self.brain_temperature = float(cfg.get("brain_temperature", 0.35))

        if not api_key or api_key == "ollama":
            if conn.provider == "ollama":
                pass
            else:
                logger.error(
                    "API ключ LLM не найден — задай в конфиге llm.api_key / openrouter.api_key "
                    "или переменную окружения для провайдера %s",
                    conn.provider,
                )

        talk_timeout = float(cfg.get("timeout_seconds", cfg.get("primary_timeout_seconds", 120.0)))
        talk_retries = int(cfg.get("max_retries", cfg.get("primary_max_retries", 1)))
        brain_timeout = float(cfg.get("brain_timeout_seconds", cfg.get("timeout_seconds", talk_timeout)))
        brain_retries = int(cfg.get("brain_max_retries", cfg.get("max_retries", talk_retries)))
        ar_cfg0 = cfg.get("async_reflection") if isinstance(cfg.get("async_reflection"), dict) else {}
        reflection_timeout = float(cfg.get("reflection_timeout_seconds", ar_cfg0.get("timeout_seconds", talk_timeout)))
        reflection_retries = int(cfg.get("reflection_max_retries", ar_cfg0.get("max_retries", talk_retries)))
        extra_body: dict[str, Any] = {}
        # Опциональные провайдер-специфичные флаги (например, для xAI/Grok).
        if "reasoning_enabled" in cfg:
            extra_body["reasoning_enabled"] = bool(cfg.get("reasoning_enabled"))
        if "include_reasoning" in cfg:
            extra_body["include_reasoning"] = bool(cfg.get("include_reasoning"))

        hdr_talk = dict(conn.default_headers)
        self.llm_talk = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=talk_model,
            temperature=cfg.get("temperature", 0.75),
            top_p=float(cfg.get("top_p", 1.0)),
            presence_penalty=float(cfg.get("presence_penalty", 0.0)),
            frequency_penalty=float(cfg.get("frequency_penalty", 0.0)),
            max_tokens=self.reply_max_tokens,
            streaming=True,
            timeout=talk_timeout,
            max_retries=talk_retries,
            model_kwargs={"extra_body": extra_body} if extra_body else {},
            default_headers=hdr_talk,
        )
        # Жестко режем попытки модели выводить think-теги в основном ответе.
        # Это снижает задержки и убирает кейсы "пустой ответ после очистки".
        self.llm_talk = self.llm_talk.bind(
            stop=["<think>", "</think>", "<thought>", "</thought>", "<redacted_thinking>", "</redacted_thinking>"]
        )

        hdr_brain = dict(conn.default_headers)
        hdr_brain["X-Title"] = "Neyra Brain"
        brain_llm_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "api_key": api_key,
            "model": brain_model,
            "temperature": self.brain_temperature,
            "top_p": float(cfg.get("brain_top_p", cfg.get("top_p", 1.0))),
            "streaming": False,
            "timeout": brain_timeout,
            "max_retries": brain_retries,
            "model_kwargs": {"extra_body": extra_body} if extra_body else {},
            "default_headers": hdr_brain,
        }
        if self.brain_max_tokens is not None:
            brain_llm_kwargs["max_tokens"] = self.brain_max_tokens
        self.llm_brain = ChatOpenAI(**brain_llm_kwargs)

        hdr_memory = dict(conn.default_headers)
        hdr_memory["X-Title"] = "Neyra Memory"
        memory_llm_kwargs: dict[str, Any] = {
            "base_url": base_url,
            "api_key": api_key,
            "model": memory_model,
            "temperature": self.reflection_temperature,
            "streaming": False,
            "timeout": reflection_timeout,
            "max_retries": reflection_retries,
            "default_headers": hdr_memory,
        }
        if self.reflection_max_tokens is not None:
            memory_llm_kwargs["max_tokens"] = self.reflection_max_tokens
        self.llm_memory = ChatOpenAI(**memory_llm_kwargs)
        self.llm_reflection = self.llm_memory
        self.llm_memory_model = memory_model
        self.llm_reflection_model = memory_model

        self.llm_primary = self.llm_talk
        self.llm = self.llm_talk
        self.llm_model = talk_model
        self.llm_talk_model = talk_model
        self.llm_primary_model = talk_model
        self.llm_brain_model = brain_model
        self.llm_fallback_model = None
        self.primary_first_token_timeout = float(cfg.get("primary_first_token_timeout_seconds", talk_timeout))
        self.async_reflection_cfg = cfg.get("async_reflection") or {}
        self.async_reflection_enabled = bool(self.async_reflection_cfg.get("enabled", False))
        self.micro_planning_cfg = cfg.get("micro_planning") or {}
        self.micro_planning_enabled = bool(self.micro_planning_cfg.get("enabled", False))
        self.micro_plan_mode = str(self.micro_planning_cfg.get("mode", "tags")).strip().lower()
        if self.micro_plan_mode not in {"tags", "anchor"}:
            self.micro_plan_mode = "tags"
        self.micro_plan_start = str(self.micro_planning_cfg.get("start_tag", "[PLAN]"))
        self.micro_plan_end = str(self.micro_planning_cfg.get("end_tag", "[/PLAN]"))
        self.micro_plan_anchor_prefix = str(self.micro_planning_cfg.get("anchor_plan", "PLAN:"))
        self.micro_plan_anchor_reply = str(self.micro_planning_cfg.get("anchor_reply", "SAY:"))
        self.micro_plan_prefill_enabled = bool(self.micro_planning_cfg.get("prefill_enabled", False))
        self._micro_plan_metrics = {
            "filtered_stream_chars": 0,
            "filtered_final_chars": 0,
            "unclosed_blocks": 0,
            "leak_detected": 0,
        }
        if str(self.async_reflection_cfg.get("model") or "").strip():
            logger.warning(
                "Deprecated: async_reflection.model игнорируется — используется openrouter.memory_model (%s).",
                memory_model,
            )

        logger.info(
            "Бэкенд LLM: %s | talk=%s brain=%s memory=%s | timeout talk=%ss retries=%s | max_ctx: %s",
            conn.provider,
            talk_model,
            brain_model,
            memory_model,
            talk_timeout,
            talk_retries,
            self.context_window,
        )
        logger.info(
            "LLM token budgets | reply=%s | brain=%s | lyrics_cap=%s | vision=%s | memory/reflection=%s | async_reflection_note_max=%s",
            self.reply_max_tokens,
            self.brain_max_tokens,
            getattr(self, "lyrics_reply_max_tokens", 0),
            self.vision_max_tokens,
            self.reflection_max_tokens,
            int(self.async_reflection_cfg.get("max_tokens", 500)),
        )
        logger.info(
            "LLM vision_model id (resolved)=%s",
            vision_model_id,
        )
        if self.async_reflection_enabled:
            logger.info(
                "Async reflection включен | memory_model=%s (поведение из async_reflection.*)",
                memory_model,
            )

        self.llm_with_tools = self.llm_brain
        self.llm_capabilities = dict(conn.capabilities)

        vis = self._vision_pipeline_cfg()
        self.llm_vision = None
        if vis.get("enabled"):
            if vis.get("use_brain_model_for_vision"):
                self.llm_vision = self.llm_brain
                logger.info(
                    "Зрение: unified brain — нативный мультимодальный ввод (%s).",
                    brain_model,
                )
            else:
                vmodel = str(vision_model_id).strip()
                hdr_vision = dict(conn.default_headers)
                hdr_vision["X-Title"] = "Neyra AI Vision"
                self.llm_vision = ChatOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    model=vmodel,
                    temperature=float(cfg.get("vision_temperature", cfg.get("temperature", 0.75))),
                    max_tokens=self.vision_max_tokens,
                    streaming=True,
                    timeout=float(cfg.get("vision_timeout_seconds", 180)),
                    model_kwargs={"extra_body": extra_body} if extra_body else {},
                    default_headers=hdr_vision,
                )
                logger.info("Зрение: VL-модель (%s) — %s", conn.provider, vmodel)

    def _vision_pipeline_cfg(self) -> dict[str, Any]:
        """Единый контур vision: openrouter.vision_model (см. core.llm_profile.merged_vision_pipeline)."""
        from core.llm_profile import merged_vision_pipeline

        return merged_vision_pipeline(self.config)

    def _uses_brain_native_vision(self) -> bool:
        return bool(self._vision_pipeline_cfg().get("use_brain_model_for_vision"))

    def _setup_memory(self):
        """Инициализирует все модули памяти."""
        from core.memory import LongTermMemory, MemoryHub, NeyraDiary, PeopleDB, ShortTermMemory

        mem_cfg = self.config.get("memory", {}) or {}
        stm_max = int(mem_cfg.get("stm_max_messages") or 10)
        self.short_memory = ShortTermMemory(max_messages=max(2, stm_max))
        self.long_memory = LongTermMemory(self.config)
        self.people_db = PeopleDB(self.config)
        self.diary = NeyraDiary(self.config)
        self.memory_hub = MemoryHub(
            self.config,
            long_memory=self.long_memory,
            event_bus=self.event_bus,
        )
        self.people_db.memory_hub = self.memory_hub
        self.diary.memory_hub = self.memory_hub
        # Hub SQLite is the source of truth for PeopleDB — always hydrate in-memory cache from it.
        try:
            self.people_db.hydrate_from_hub(self.memory_hub)
        except Exception as e:
            logger.warning("PeopleDB hydrate_from_hub failed: %s", e)

        # Не блокируем старт бота тяжёлой загрузкой embedder'а:
        # RAG поднимется в фоне, а при первом запросе есть ленивый fallback.
        if bool(mem_cfg.get("rag_init_in_background", True)):
            logger.info("Инициализирую долгосрочную память в фоне...")
            self.long_memory.initialize_async()
        else:
            logger.info("Инициализирую долгосрочную память...")
            self.long_memory.initialize()

        # Создаём начальные досье если их нет
        self._init_people_db()

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
        from .chat_log import append_turn_to_chat_log

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
        from core.tools import ALL_TOOLS, init_tools

        init_tools(
            self.long_memory,
            self.people_db,
            self.config.get("assistant") or {},
            neyra_config=self.config,
            memory_hub=self.memory_hub,
        )
        self.tools = {t.name: t for t in ALL_TOOLS}
        self.mcp_manager = None
        self._mcp_merge_done = False
        mc = self.config.get("mcp_client") if isinstance(self.config.get("mcp_client"), dict) else {}
        if mc.get("enabled"):
            from core.mcp_client import MCPClientManager

            self.mcp_manager = MCPClientManager(self.config)
        logger.info(f"Tools готовы: {list(self.tools.keys())}")

    async def start_mcp_clients(self) -> None:
        """Подключить MCP-серверы и добавить динамические tools (идемпотентно)."""
        await self._ensure_mcp()

    async def stop_mcp_clients(self) -> None:
        if not self.mcp_manager:
            return
        try:
            await self.mcp_manager.stop()
        except Exception as e:
            logger.debug("MCP stop: %s", e)
        self._mcp_merge_done = False

    async def _ensure_mcp(self) -> None:
        if self._mcp_merge_done or not self.mcp_manager:
            return
        try:
            await self.mcp_manager.start()
        except Exception as e:
            logger.exception("MCP: не удалось запустить клиенты: %s", e)
        try:
            for t in self.mcp_manager.get_langchain_tools():
                self.tools[t.name] = t
        except Exception as e:
            logger.warning("MCP: список инструментов недоступен: %s", e)
        self._mcp_merge_done = True
        logger.info("MCP: после merge доступно tools=%s", len(self.tools))

    def _setup_logs(self):
        """Создаёт директории и файлы для логов."""
        mem_cfg = self.config.get("memory", {})
        log_cfg = self.config.get("logging", {})

        self.thoughts_log_path = Path(mem_cfg.get("thoughts_log", "./memory/thoughts.log"))
        self.chat_log_path = Path(log_cfg.get("chat_log", "./logs/chat.log"))

        self.thoughts_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.chat_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_people_db(self):
        """Засеивает базовые досье, только если Hub/PeopleDB ещё пусты (никакого JSON-импорта)."""
        hub = getattr(self, "memory_hub", None)
        if hub is not None:
            try:
                people_n = int(hub.stats().get("people") or 0)
            except Exception:
                people_n = 0
            if people_n > 0 or self.people_db._cache:
                return
        else:
            if self.people_db._cache:
                return

        logger.info("Создаю начальные досье PeopleDB...")

        people = [
            {
                "id": "maxim",
                "names": ["Максим", "МаксимкусЮТ", "tiltedeverlastinghat", "hopelesness"],
                "discord_ids": [],
                "static_facts": {
                    "birth_year": 2004,
                    "city": "Киров",
                    "living": "квартира на кирпичке с мамой, бабушкой и братом Димой ~4г",
                    "work": "безработный",
                    "games": ["Roblox", "Dota 2", "CS2"],
                    "notes": "Аниме на аве. Подкалывать за безработность и Роблокс."
                },
                "dynamic_facts": [],
            },
            {
                "id": "kutyr",
                "names": ["Дмитрий", "Кутырин", "zalupank", "димас", "кутыр", "таксист на ауди"],
                "discord_ids": [],
                "static_facts": {
                    "birth_year": 2005,
                    "city": "Киров",
                    "living": "с девушкой, каблук",
                    "car": "старая Ауди",
                    "games": ["Dota 2", "CS2"],
                    "trigger": "Бесится когда называют 'Иван Золо'",
                    "notes": "Аниме на аве. Шутить про Ауди можно, но в меру."
                },
                "dynamic_facts": [],
            },
            {
                "id": "timofey",
                "names": ["Тимофей", "maj14", "маджестик", "maji", "тимоша", "тимдимыч"],
                "discord_ids": [],
                "static_facts": {
                    "age": "~19",
                    "city": "Волгоград",
                    "study": "пилот БПЛА, колледж/шарага",
                    "games": ["Garry's Mod (Postbellum ~4k ч)", "Dota 2"],
                    "traits": "Везучее говно, говноед. Везёт на смены региона в Роблокс.",
                    "notes": "Аниме на аве. Можно жёстко стебать — не обижается."
                },
                "dynamic_facts": [],
            },
            {
                "id": "andrey_griniks",
                "names": ["Андрей", "Гриникс", "гриндук", "гринишка", "андрейка", "школьник"],
                "discord_ids": [],
                "static_facts": {
                    "grade": "11 класс",
                    "traits": "немного тупенький, молчит или мычит",
                    "games": ["Genshin Impact", "Dota 2"],
                    "girlfriend": "Вика (иногда писали ей в ВК чтоб отпустила)"
                },
                "dynamic_facts": [],
            },
            {
                "id": "bogdan",
                "names": ["Богдан", "zБИГден", "бигденчик", "psiqq"],
                "discord_ids": [],
                "static_facts": {
                    "relation_to": "одноклассник Тимофея",
                    "traits": "толстый (сам шутит — говорит сиськи >3 размера)",
                    "frequency": "заходит редко",
                    "rule": "КАК ТОЛЬКО ПОЯВЛЯЕТСЯ В ВОЙСЕ — СЛАТЬ НАХУЙ"
                },
                "dynamic_facts": [],
            },
            {
                "id": "foxy",
                "names": ["Андрей Иванцов", "Фокси", "Иванцов", "Водитель ШНИВЫ"],
                "discord_ids": [],
                "static_facts": {
                    "birth_year": "~2005",
                    "city": "Киров",
                    "work": "бывший курьер, теперь перекуп",
                    "car": "Шевроле Нива 2005 — ПОДАРОК ОТЦА, ТАБУ",
                    "girlfriend": "Ксюша (никому не нравится характер)",
                    "notes": "В дискорде не сидит. Про Ниву — МОЛЧАТЬ. Про Ксюшу только если сами начали."
                },
                "dynamic_facts": [],
            },
            {
                "id": "erik",
                "names": ["Эрик", "Хачик", "Армянин", "Сарибек", "Арзоян", "Чурка"],
                "discord_ids": [],
                "static_facts": {
                    "city": "Киров (рядом с Димой)",
                    "car": "Lada",
                    "traits": "клички принимает и не обиждается",
                    "notes": "В дискорде не сидит."
                },
                "dynamic_facts": [],
            },
        ]

        for person in people:
            person.setdefault("last_seen", None)
            self.people_db._cache[person["id"]] = person
            if hub is not None:
                try:
                    hub.upsert_person(
                        person["id"],
                        display_name=(person.get("names") or [person["id"]])[0],
                        aliases=list(person.get("names") or []),
                        meta=person,
                    )
                except Exception as e:
                    logger.warning("PeopleDB seed→Hub failed for %s: %s", person["id"], e)

        logger.info(f"Создано {len(people)} начальных досье")

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
        from .prompts import build_talk_system_prompt

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
        from .prompts import build_brain_system_prompt

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
        from langchain_core.messages import AIMessage as LC_AIMessage
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

        parts: list[str] = []
        um = (user_message or "").strip()
        if um:
            parts.append(self._format_spoken_user_message(um, speaker_label))
        vc = (vision_caption or "").strip()
        if vc and not vision_images:
            parts.append("[Конспект изображения VL]\n" + vc)
        human_content = "\n\n".join(parts) if parts else "(пустое сообщение)"
        if lyrics_mode:
            human_content += "\n\n[Оговорка] Пользователь запросил режим текста песни — учитывай для инструментов/поиска."

        if vision_images:
            human_msg = self._make_human_turn(
                um or "Что на изображении? Учти контекст для инструментов.",
                vision_images,
                speaker_label=speaker_label,
            )
            if vc:
                extra = "\n\n[Доп. контекст VL]\n" + vc
                if isinstance(human_msg.content, list):
                    human_msg.content[0]["text"] = str(human_msg.content[0].get("text", "")) + extra
                else:
                    human_msg = HumanMessage(content=str(human_msg.content) + extra)
        else:
            human_msg = HumanMessage(content=human_content)

        messages: list[Any] = [
            SystemMessage(content=brain_system),
            human_msg,
        ]

        mcp_cfg = self.config.get("mcp_client") if isinstance(self.config.get("mcp_client"), dict) else {}
        use_tool_loop = bool(mcp_cfg.get("llm_tool_calls")) and bool(self.tools)
        max_tool_steps = max(1, int(mcp_cfg.get("llm_tool_max_steps", 4)))

        brain_llm = self.llm_brain
        if lyrics_mode:
            cap = self.lyrics_reply_max_tokens
            if self.brain_max_tokens is not None:
                cap = max(self.brain_max_tokens, cap)
            brain_llm = self.llm_brain.bind(max_tokens=cap)

        try:
            if not use_tool_loop:
                response = await self._ainvoke_text_with_fallback(messages, llm=brain_llm)
                self._log_model_route(self._extract_model_name(response), lane="brain")
                text = response.content if hasattr(response, "content") else str(response)
                return (text or "").strip()

            bound = brain_llm.bind_tools(list(self.tools.values()))
            step = 0
            response = None
            while step < max_tool_steps:
                response = await self._ainvoke_text_with_fallback(messages, llm=bound)
                self._log_model_route(self._extract_model_name(response), lane="brain")
                tcalls = getattr(response, "tool_calls", None) if isinstance(response, LC_AIMessage) else None
                if not tcalls:
                    break
                messages.append(response)
                for tc in tcalls:
                    if isinstance(tc, dict):
                        tid = str(tc.get("id") or "")
                        tname = str(tc.get("name") or "")
                        args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                    else:
                        tid = str(getattr(tc, "id", None) or "")
                        tname = str(getattr(tc, "name", None) or "")
                        args = getattr(tc, "args", None) or {}
                        if not isinstance(args, dict):
                            args = {}
                    if not tname:
                        continue
                    out = await self._execute_tool(tname, **args)
                    messages.append(ToolMessage(content=out, tool_call_id=tid))
                step += 1
            if response is None:
                response = await self._ainvoke_text_with_fallback(messages, llm=brain_llm)
                self._log_model_route(self._extract_model_name(response), lane="brain")
            text = response.content if hasattr(response, "content") else str(response)
            return (text or "").strip()
        except Exception as e:
            logger.warning("Brain phase: ошибка, talk продолжит без сводки brain: %s", e)
            return ""

    def _make_vision_memory_note(self, thoughts: str, clean_text: str) -> str:
        """Текст для «памяти последнего скрина»: приоритет — CoT/think из ответа VL."""
        vis = self._vision_pipeline_cfg()
        max_c = int(vis.get("last_image_note_max_chars", 1200))
        t = (thoughts or "").strip()
        if t:
            body = t
        else:
            c = (clean_text or "").strip()
            if not c:
                return ""
            body = (
                "(в ответе API не было блока think/thought) Кратко что ответила по скрину: "
                + c
            )
        if len(body) > max_c:
            body = body[: max_c - 1] + "…"
        return body

    def _last_image_context_for_prompt(
        self,
        channel_id: Optional[str],
        vision_images: Optional[list],
    ) -> Optional[str]:
        vis_cfg = self._vision_pipeline_cfg()
        if not vis_cfg.get("remember_last_image", True) or vision_images or not channel_id:
            return None
        return self._last_vision_note_by_channel.get(str(channel_id))

    def _store_vision_note_if_needed(
        self,
        channel_id: Optional[str],
        vision_images: Optional[list],
        thoughts: str,
        clean_text: str,
    ) -> None:
        if not channel_id or not vision_images:
            return
        vis = self._vision_pipeline_cfg()
        if not vis.get("remember_last_image", True):
            return
        note = self._make_vision_memory_note(thoughts, clean_text)
        if note:
            self._last_vision_note_by_channel[str(channel_id)] = note
            logger.debug("Зрение: заметка по каналу %s (%s симв.)", channel_id, len(note))

    def _resolve_speaker_label(
        self,
        username: Optional[str],
        discord_user_id: Optional[str],
        author_display_name: Optional[str] = None,
    ) -> str:
        """Подпись собеседника для STM, HumanMessage и system prompt (этап B1)."""
        from .speakers import resolve_speaker_label

        return resolve_speaker_label(
            self.memory_hub, username, discord_user_id, author_display_name
        )

    def _format_spoken_user_message(self, text: str, speaker_label: str) -> str:
        """Префикс авторства реплики в контексте LLM ([Пользователь …]: …)."""
        from .speakers import format_spoken_user_message

        return format_spoken_user_message(text, speaker_label)

    def _make_human_turn(
        self,
        user_message: str,
        vision_images: Optional[list[tuple[str, str]]] = None,
        *,
        speaker_label: Optional[str] = None,
    ):
        """HumanMessage: текст или мультимодальный контент (mime, base64) для VL."""
        from .speakers import make_human_turn

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
        """Пытается достать model name из response_metadata/metadata LangChain объекта."""
        md = getattr(payload, "response_metadata", None) or {}
        if isinstance(md, dict):
            model = md.get("model_name") or md.get("model")
            if model:
                return str(model)
        md2 = getattr(payload, "metadata", None) or {}
        if isinstance(md2, dict):
            model = md2.get("model_name") or md2.get("model")
            if model:
                return str(model)
        return None

    def _log_model_route(self, used_model: Optional[str], *, lane: str = "talk") -> None:
        if not used_model:
            return
        primary = str(getattr(self, "llm_primary_model", "") or "")
        fallback = str(getattr(self, "llm_fallback_model", "") or "")
        route = "primary"
        if fallback and fallback in used_model:
            route = "fallback"
        logger.info("LLM route | lane=%s | route=%s | model=%s", lane, route, used_model)

    async def _run_async_reflection(
        self,
        user_message: str,
        assistant_text: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        if not self.async_reflection_enabled:
            return
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            ar = self.async_reflection_cfg if isinstance(self.async_reflection_cfg, dict) else {}
            ar_bind: dict[str, Any] = {
                "temperature": float(ar.get("temperature", self.reflection_temperature)),
            }
            ar_max = ar.get("max_tokens")
            if ar_max is not None:
                ar_bind["max_tokens"] = int(ar_max)
            elif self.reflection_max_tokens is not None:
                ar_bind["max_tokens"] = self.reflection_max_tokens
            else:
                ar_bind["max_tokens"] = 500
            llm_ar = self.llm_memory.bind(**ar_bind)

            sys_prompt = (
                "Ты внутренний аналитический модуль Нейры. "
                "Сформируй краткий (4-8 предложений) анализ микро-диалога: "
                "намерение пользователя, эмоции, качество ответа и что стоит запомнить на будущее. "
                "Не пиши теги <think>, markdown и служебные поля."
            )
            human = (
                f"Пользователь ({username or 'unknown'}, discord_id={discord_user_id or ''}) сказал:\n"
                f"{user_message}\n\n"
                f"Нейра ответила:\n{assistant_text}\n\n"
                "Сделай полезную заметку для дневника."
            )
            from core.llm_retry import ainvoke_with_rate_limit_backoff

            resp = await ainvoke_with_rate_limit_backoff(
                llm_ar,
                [SystemMessage(content=sys_prompt), HumanMessage(content=human)],
                lane="memory_model",
            )
            note = (resp.content if hasattr(resp, "content") else str(resp)).strip()
            note = re.sub(r"\s+", " ", note).strip()
            if not note:
                return
            if len(note) > int(self.async_reflection_cfg.get("max_note_chars", 1200)):
                note = note[: int(self.async_reflection_cfg.get("max_note_chars", 1200)) - 1] + "…"
            self.diary.add_entry(
                text=note,
                source="async_reflection",
                meta={"username": username or "unknown", "discord_id": discord_user_id or ""},
            )
            logger.debug("Async reflection: запись в дневник добавлена (%s симв.)", len(note))
        except Exception as e:
            logger.warning("Async reflection ошибка: %s", e)

    def _schedule_async_reflection(
        self,
        user_message: str,
        assistant_text: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        if not self.async_reflection_enabled:
            return
        try:
            asyncio.create_task(
                self._run_async_reflection(
                    user_message=user_message,
                    assistant_text=assistant_text,
                    username=username,
                    discord_user_id=discord_user_id,
                )
            )
        except Exception as e:
            logger.warning("Не удалось запланировать async reflection: %s", e)

    def _format_stm_tail(self, max_messages: int = 12) -> str:
        lines: list[str] = []
        for m in self.short_memory.get_history()[-max_messages:]:
            role = str(m.get("role") or "")
            content = str(m.get("content") or "")
            label = "Пользователь" if role == "user" else "Нейра"
            chunk = content if len(content) <= 1600 else content[:1597] + "…"
            lines.append(f"{label}: {chunk}")
        return "\n".join(lines)

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
        from core.memory import working_memory as wm

        await wm.refresh_working_memory_async(
            self,
            self.config,
            root=self._project_root,
            internal_user_id=internal_user_id,
            user_message=user_message,
            assistant_text=assistant_text,
            stm_tail=self._format_stm_tail(12),
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
        from core.memory import working_memory as wm

        if not wm.wm_enabled(self.config):
            return
        cfg = wm.wm_config(self.config)
        force = bool(stm_trimmed and cfg.get("update_after_context_trim", True))
        self._wm_turns_since_refresh += 1
        every = max(1, int(cfg.get("update_every_n_turns", 2)))
        should = force or self._wm_turns_since_refresh >= every
        if not should:
            return
        gap = float(cfg.get("min_interval_seconds", 30))
        if gap > 0 and not force and (time.monotonic() - self._wm_last_refresh_mono) < gap:
            return
        self._wm_turns_since_refresh = 0
        self._wm_last_refresh_mono = time.monotonic()
        try:
            asyncio.create_task(
                self._run_working_memory_refresh(
                    internal_user_id=internal_user_id,
                    user_message=user_message,
                    assistant_text=assistant_text,
                    speaker_label=speaker_label,
                    reason="context_trim" if stm_trimmed else f"every_{every}_turns",
                )
            )
        except Exception as e:
            logger.warning("Не удалось запланировать working_memory: %s", e)

    async def _save_dialog_to_ltm_with_emotion(
        self,
        user_message: str,
        clean_text: str,
        metadata: dict,
        speaker_label: str,
    ) -> None:
        from core.memory import emotional_layer as el

        md = dict(metadata)
        if el.layer_enabled(self.config) and el.layer_cfg(self.config).get("ltm_emotion_sync"):
            tag = await el.compact_emotion_for_ltm(
                self,
                self.config,
                user_message=user_message,
                assistant_text=clean_text,
                speaker_label=speaker_label,
            )
            if tag:
                md["assistant_emotion"] = tag
        hub = getattr(self, "memory_hub", None)
        if hub is not None:
            hub.save_dialog_semantic(user_message, clean_text, md)
        else:
            self.long_memory.save(user_message, clean_text, md)

    def _schedule_emotion_diary(
        self,
        *,
        user_message: str,
        assistant_text: str,
        speaker_label: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        from core.memory import emotional_layer as el

        if not el.layer_enabled(self.config) or not el.layer_cfg(self.config).get("diary_after_turn", True):
            return
        gap = float(el.layer_cfg(self.config).get("diary_emotion_min_interval_seconds", 90))
        if gap > 0 and (time.monotonic() - self._emotion_last_mono) < gap:
            return
        self._emotion_last_mono = time.monotonic()
        try:
            asyncio.create_task(
                el.diary_emotion_after_turn_async(
                    self,
                    self.config,
                    user_message=user_message,
                    assistant_text=assistant_text,
                    speaker_label=speaker_label,
                    username=username,
                    discord_user_id=discord_user_id,
                )
            )
        except Exception as e:
            logger.warning("Не удалось запланировать emotional_layer diary: %s", e)

    async def _ainvoke_text_with_fallback(self, messages: list[Any], *, llm=None):
        """Обычный нестриминговый вызов (одна модель)."""
        model = llm or self.llm_talk
        return await model.ainvoke(messages)

    async def _astream_text_with_fallback(self, messages: list[Any], *, llm=None):
        """Стриминговый вызов live-модели с guard по first-token timeout и 1 ретраем."""
        model = llm or self.llm_talk
        first_timeout = max(0.1, float(getattr(self, "primary_first_token_timeout", 8.0)))
        attempts = 2
        last_err: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            stream = model.astream(messages)
            it = stream.__aiter__()
            try:
                first_chunk = await asyncio.wait_for(it.__anext__(), timeout=first_timeout)
                first_token = first_chunk.content if hasattr(first_chunk, "content") else str(first_chunk)
                if first_token:
                    route = "primary" if attempt == 1 else "primary_retry"
                    logger.info("LLM first token | route=%s | delay=%.3fs", route, time.monotonic() - started)
                yield first_chunk
                async for ch in it:
                    yield ch
                return
            except asyncio.TimeoutError as e:
                last_err = e
                logger.warning(
                    "LLM first-token timeout | attempt=%s/%s | timeout=%.1fs",
                    attempt,
                    attempts,
                    first_timeout,
                )
                continue
            except StopAsyncIteration:
                return
            except Exception as e:
                last_err = e
                if attempt >= attempts:
                    raise
                logger.warning("LLM stream attempt failed, retrying same model: %s", e)
                continue

        if last_err:
            raise last_err

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
        """
        Если новый ответ почти дублирует предыдущий ответ ассистента,
        делаем быструю переформулировку, чтобы не зацикливаться.
        """
        if LYRICS_REQUEST_MARKER in (user_message or ""):
            return (clean_text or "").strip()
        text = (clean_text or "").strip()
        if not text:
            return text
        hist = self.short_memory.get_history()
        prev_assistant = ""
        for msg in reversed(hist):
            if msg.get("role") == "assistant":
                prev_assistant = str(msg.get("content") or "").strip()
                break
        if not prev_assistant:
            return text

        sim = SequenceMatcher(None, prev_assistant.lower(), text.lower()).ratio()
        if sim < 0.92:
            return text

        logger.warning("Anti-repeat: похожий ответ (similarity=%.2f), делаю перефраз", sim)
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            rewrite_llm = self.llm_talk.bind(max_tokens=90, temperature=0.9)
            resp = await rewrite_llm.ainvoke(
                [
                    SystemMessage(
                        content=(
                            "Перефразируй реплику ассистента по-русски: коротко, живо, без markdown, "
                            "без тегов <think>/<thought>, без копирования той же фразы."
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"Запрос пользователя: {user_message}\n"
                            f"Предыдущая реплика ассистента: {prev_assistant}\n"
                            f"Новая реплика-клон: {text}\n"
                            "Нужна новая формулировка с тем же смыслом."
                        )
                    ),
                ]
            )
            raw = resp.content if hasattr(resp, "content") else str(resp)
            text_no_think, _ = self._extract_think_blocks(raw)
            alt, _ = self._extract_sound_tags(text_no_think)
            alt = (alt or "").strip()
            if alt and alt.lower() != prev_assistant.lower():
                return alt
        except Exception as e:
            logger.warning("Anti-repeat перефраз не удался: %s", e)
        return text

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
        from .people_context import detect_mentioned_names

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
        from .people_context import split_people_context

        return split_people_context(self.memory_hub, mentioned, username, discord_user_id)

    @staticmethod
    def _shrink_people_sections(active: str, mentioned: str, max_chars: int) -> tuple[str, str]:
        """Ужимает блоки досье при переполнении контекста; приоритет — активный собеседник."""
        from .people_context import shrink_people_sections

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
        """
        Детерминированный вызов tools по эвристикам.
        Идея: меньше ждать триггер-слов, чаще подмешивать релевантную память/досье автоматически.
        """
        parts: list[str] = []
        tl = text.lower().strip()

        time_phrases = (
            "который час",
            "сколько времени",
            "какое время",
            "которая сейчас дата",
            "какой сегодня день",
            "какая сегодня дата",
            "какое сегодня число",
        )
        if any(p in tl for p in time_phrases) and "погода" not in tl:
            try:
                out = self.tools["get_current_time"].invoke({})
                parts.append(f"[время]\n{out}")
            except Exception as e:
                logger.debug("get_current_time: %s", e)

        sys_markers = (
            "железо",
            "загрузка проц",
            "загрузка цп",
            "оператив",
            "uptime",
            "сколько места",
            "место на диск",
            " диск ",
            "диск ",
            "озу ",
        )
        if ("систем" in tl and "контекст" not in tl) or any(s in tl for s in sys_markers):
            cmd = "uptime"
            if "диск" in tl or "место" in tl:
                cmd = "disk"
            elif "оператив" in tl or "озу" in tl:
                cmd = "memory"
            elif "проц" in tl or "cpu" in tl or "цп" in tl:
                cmd = "cpu"
            elif "python" in tl:
                cmd = "python"
            try:
                raw = self.tools["check_system"].invoke({"command": cmd})
                parts.append(f"[система:{cmd}]\n{raw[:2500]}")
            except Exception as e:
                logger.debug("check_system: %s", e)

        # Долгосрочная память (RAG) — явные фразы
        mem_starts = ("вспомни про", "вспомни что", "вспомни,", "что мы говорили про", "что мы обсуждали")
        mem_extra = ("найди в памяти", "поиск в памяти")
        wants_mem = self.long_memory.rag_enabled and (
            (tl.startswith("вспомни ") and len(text.strip()) > 10)
            or any(m in tl for m in mem_starts)
            or any(m in tl for m in mem_extra)
        )
        if wants_mem:
            q = text.strip()
            low = q.lower()
            for prefix in ("вспомни про ", "вспомни что ", "вспомни, ", "вспомни "):
                if low.startswith(prefix):
                    q = q[len(prefix) :].strip()
                    break
            else:
                for needle in ("что мы говорили про ", "что мы обсуждали ", "найди в памяти ", "поиск в памяти диалог "):
                    if needle in low:
                        q = q[low.find(needle) + len(needle) :].strip()
                        break
            if len(q) < 3:
                q = text.strip()
            try:
                out = self.tools["search_memory"].invoke({"query": q[:800]})
                parts.append(f"[память]\n{out[:3000]}")
            except Exception as e:
                logger.debug("search_memory: %s", e)

        import re

        m = re.search(r"(?:досье|инфа)\s+(?:на|про)\s+(.+)", text.strip(), flags=re.IGNORECASE)
        if m:
            who = m.group(1).strip().strip("?.!, ")
            if who:
                try:
                    out = self.tools["get_person_info"].invoke({"name_or_id": who[:120]})
                    parts.append(f"[досье:{who}]\n{out[:2500]}")
                except Exception as e:
                    logger.debug("get_person_info: %s", e)

        # Автодосье: если упомянуто известное имя, подмешиваем краткую справку без явной команды.
        try:
            mentioned = self._detect_mentioned_names(text)
            for pid in mentioned[:2]:
                out = self.tools["get_person_info"].invoke({"name_or_id": pid})
                parts.append(f"[авто-досье:{pid}]\n{str(out)[:1400]}")
        except Exception as e:
            logger.debug("auto get_person_info: %s", e)

        # Автопамять: если похоже на продолжение темы/контекста, запрашиваем RAG без ключевого слова "вспомни".
        mem_hints = (
            "помнишь",
            "как там",
            "что там было",
            "мы говорили",
            "раньше",
            "вчера",
            "в прошлый раз",
            "опять про",
            "продолжим",
        )
        if self.long_memory.rag_enabled and (
            any(h in tl for h in mem_hints)
            or (len(tl) >= 18 and ("кто " in tl or "что " in tl or "почему " in tl) and "?" in tl)
        ):
            try:
                out = self.tools["search_memory"].invoke({"query": text[:800]})
                parts.append(f"[авто-память]\n{str(out)[:2200]}")
            except Exception as e:
                logger.debug("auto search_memory: %s", e)

        # Авто-подстройка характера: если юзер просит тон/манеру, добавляем профиль характера.
        style_hints = ("будь", "говори", "тон", "стиль", "помягче", "пожестче", "характер")
        if any(h in tl for h in style_hints):
            try:
                out = self.tools["get_character_profile"].invoke({})
                parts.append(f"[профиль-характера]\n{str(out)[:900]}")
            except Exception as e:
                logger.debug("get_character_profile: %s", e)

        return "\n\n".join(parts) if parts else ""

    # ─── Главный метод: генерация ответа ──────────────────────────────────

    def _handle_memory_trigger(self, text: str, mentioned: list[str], username: str) -> list[str]:
        """Эвристический поиск просьб что-то запомнить. (Фаза 2.5 — обход слабости 8B моделей)"""
        saved: list[str] = []
        text_lower = text.lower()
        if any(w in text_lower for w in ["запиши", "запомни", "добавь"]):
            
            # ЗАЩИТА ОТ ВЗЛОМА: Пользователи не могут перезаписывать критические роли
            # Только ebluffy может записывать странные вещи.
            if username != "ebluffy":
                # Запрещаем записывать факты, в которых они пытаются переписать хоста или удалить память
                forbidden = ["хозяин", "создатель", "владелец", "лучше чем", "забудь", "удали", "перепиши"]
                if any(bad in text_lower for bad in forbidden):
                    logger.warning(f"Блокирована попытка взлома памяти от {username}: {text}")
                    return saved

            import re
            match = re.search(r"(?:запиши|запомни|добавь)[^:,]*(?:[:,]\s*|что\s+)(.+)", text, flags=re.IGNORECASE)
            # Убираем возможный мусор типа обращений
            raw_fact = match.group(1).strip() if match else text
            if len(raw_fact) < 5: 
                return saved

            fact = f"(Со слов {username or 'друга'}): {raw_fact}"

            # Кому сохраняем? Если в тексте упомянуты конкретные люди, сохраняем ИМ.
            # Иначе сохраняем самому отправителю.
            author_p = self.memory_hub.find_person(username) if username else None
            
            # Автор сам всегда попадает в mentioned из-за логики chat_stream, вычистим его для поиска "кого упомянули"
            mentioned_others = [m for m in mentioned if not (author_p and m == author_p["id"])]
            
            if mentioned_others:
                targets = mentioned_others
            elif author_p:
                targets = [author_p["id"]]
            else:
                targets = []

            for uid in targets:
                if self.people_db.update_fact(uid, fact):
                    saved.append(f"{uid}: {raw_fact}")
        return saved

    def add_diary_entry(self, text: str, source: str = "manual", meta: Optional[dict] = None) -> bool:
        """Ручная запись в личный дневник Нейры."""
        return self.diary.add_entry(text=text, source=source, meta=meta)

    def get_recent_diary(self, limit: int = 12) -> str:
        return self.memory_hub.diary_recent_text(limit=limit) or "Дневник пока пуст."

    def _handle_websearch_trigger(self, text: str) -> str:
        """Эвристический веб-поиск: актуальные темы/новости/фактуальные вопросы без явных триггеров."""
        text_lower = text.lower()

        # Guard: не запускаем авто-websearch для внутренних задач разработки/плагинов.
        # Такие запросы должны обрабатываться tool-loop (например, create_or_edit_plugin), а не “гуглением”.
        internal_dev_markers = (
            "create_or_edit_plugin",
            "plugin.yaml",
            "main_script",
            "hot-reload",
            "hot reload",
            "rollback",
            "плагин",
            "плагины",
            "interfaces/",
            "interfaces\\",
            "core/",
            "core\\",
            "нейра",
        )
        if any(m in text_lower for m in internal_dev_markers):
            return ""
        
        # Спец-обработка для точной погоды
        if "погода" in text_lower:
            try:
                import requests
                import re
                match = re.search(r"погода(?: в)?\s+([а-яА-Яa-zA-Z\-]+)", text_lower)
                city = match.group(1) if match else "Воронеж"
                res = requests.get(f"https://wttr.in/{city}?format=%l:+%c+%t,+ветер+%w,+влажность+%h", timeout=5)
                if res.status_code == 200:
                    weather_text = res.content.decode('utf-8').strip()
                    # Чистим графические эмодзи, чтобы Нейра их не подхватила
                    weather_text = re.sub(r'[^\w\s\.,:\+\-°%]', '', weather_text)
                    logger.info(f"Сработал триггер Погода: {weather_text}")
                    return f"Результат поиска (Погода в реальном времени): {weather_text}"
            except Exception as e:
                logger.error(f"Weather heuristic error: {e}")
                
        triggers = ["новости", "найди", "погугли", "гугл", "интернет", "кто так", "что так"]
        fresh_markers = (
            "сегодня",
            "сейчас",
            "последние",
            "актуаль",
            "в этом году",
            "в 2025",
            "в 2026",
            "новое",
            "обновлен",
        )
        factual_question = (
            "?" in text_lower
            and any(q in text_lower for q in ("кто", "что", "где", "когда", "почему", "сколько"))
            and len(text_lower) > 22
        )
        # Если вопрос явно про личный контекст/память — не уводим в веб.
        personal_markers = ("мы", "помнишь", "про меня", "досье", "в памяти", "наш", "мой")
        wants_web = (
            any(t in text_lower for t in triggers)
            or any(t in text_lower for t in fresh_markers)
            or factual_question
        ) and not any(pm in text_lower for pm in personal_markers)

        if wants_web:
            try:
                logger.info("Авто-WebSearch: %s", text[:140])
                out = self.tools["web_search"].invoke({"query": text[:500]})
                if out:
                    return str(out)[:2200]
            except Exception as e:
                logger.error(f"Heuristic WebSearch ошибка: {e}")
        
        return ""

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
        from .turn_events import publish_memory_and_chat_events

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
        from .turn_events import publish_chat_turn_failed

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
        from langchain_core.messages import HumanMessage, SystemMessage

        internal_uid = self._resolve_internal_user_id(discord_user_id, username)
        await self._ensure_mcp()

        # 1. Ищем воспоминания в RAG
        memories = self.long_memory.search(user_message)

        # 2. Ищем упомянутых людей
        mentioned = self._detect_mentioned_names(user_message)
        if username:
            person = self.memory_hub.find_person(username, discord_id=discord_user_id)
            if person and person["id"] not in mentioned:
                mentioned.append(person["id"])

        # Эвристика: ручное сохранение фактов
        saved_facts = self._handle_memory_trigger(user_message, mentioned, username)

        people_active, people_others = self._split_people_context_for_prompt(
            mentioned, username, discord_user_id
        )
        diary_ctx = self.memory_hub.diary_recent_text(limit=6)

        # Эвристический веб-поиск
        web_ctx = self._handle_websearch_trigger(user_message)
        tool_ctx = self._collect_tool_context(user_message)

        speaker_label = self._resolve_speaker_label(username, discord_user_id, author_display_name)

        wm_snip = self._read_working_memory_for_prompt(internal_uid)

        has_vis = bool(vision_images)
        last_img_ctx = self._last_image_context_for_prompt(channel_id, vision_images)
        lyrics_mode = LYRICS_REQUEST_MARKER in (user_message or "")

        mcp_cfg = self.config.get("mcp_client") if isinstance(self.config.get("mcp_client"), dict) else {}
        mcp_catalog = ""
        if mcp_cfg.get("inject_tool_catalog") and self.mcp_manager:
            ml = self.mcp_manager.catalog_lines()
            if ml:
                mcp_catalog = "\n".join(ml)

        brain_native_vis = bool(vision_images) and self._uses_brain_native_vision()
        attached_caption = ""
        if vision_images and not brain_native_vis and self.llm_vision and self.llm_vision is not self.llm_brain:
            try:
                attached_caption = await self._caption_vision_images(
                    user_message, vision_images, speaker_label=speaker_label
                )
            except Exception as e:
                logger.warning("VL caption: ошибка, продолжаю без конспекта: %s", e)
        elif vision_images and not brain_native_vis and not self.llm_vision:
            logger.warning(
                "Изображения в сообщении, но vision/VL не настроено — ответ только по тексту."
            )

        caption_ok = (attached_caption or "").strip()
        if brain_native_vis:
            talk_vm = None
            has_vis_prompt = False
        else:
            talk_vm = None if (vision_images and self.llm_vision) else vision_images
            has_vis_prompt = bool(vision_images) and not caption_ok and self.llm_vision is None

        brain_sys = self._build_brain_system_prompt(
            extra_memories=memories,
            people_context_active=people_active,
            people_context_mentioned=people_others,
            diary_context=diary_ctx,
            username=speaker_label,
            web_context=web_ctx,
            tool_context=tool_ctx,
            mcp_tools_catalog=mcp_catalog,
            last_image_context=last_img_ctx,
            working_memory_context=wm_snip,
        )
        brain_context = ""
        try:
            brain_context = await self._run_brain_tool_phase(
                user_message=user_message,
                speaker_label=speaker_label,
                vision_caption=caption_ok or None,
                vision_images=vision_images if brain_native_vis else None,
                brain_system=brain_sys,
                lyrics_mode=lyrics_mode,
            )
        except Exception as e:
            logger.warning("Brain phase: пропуск сводки — %s", e)

        # 3. Системный промпт (talk)
        system_prompt = self._build_system_prompt(
            extra_memories=memories,
            people_context_active=people_active,
            people_context_mentioned=people_others,
            diary_context=diary_ctx,
            username=speaker_label,
            web_context=web_ctx,
            tool_context=tool_ctx,
            has_vision_images=has_vis_prompt,
            last_image_context=last_img_ctx,
            lyrics_mode=lyrics_mode,
            mcp_tools_catalog=mcp_catalog,
            brain_router_context=brain_context or "",
            attached_image_caption=caption_ok,
            working_memory_context=wm_snip,
        )

        # 4. Строим список сообщений
        messages = [SystemMessage(content=system_prompt)]

        # Добавляем историю диалога
        for msg in self.short_memory.get_history():
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=msg["content"]))

        # Текущее сообщение
        messages.append(
            self._make_human_turn(user_message, talk_vm, speaker_label=speaker_label)
        )
        messages = self._maybe_append_micro_plan_prefill(
            messages,
            has_vision_images=bool(vision_images) and not brain_native_vis and self.llm_vision is None,
        )
        final_messages_used = messages

        # 5. Вызов LLM (talk only)
        try:
            cap_llm = (
                self.llm_talk.bind(max_tokens=max(self.reply_max_tokens, self.lyrics_reply_max_tokens))
                if lyrics_mode
                else self.llm_talk
            )
            response = await self._ainvoke_text_with_fallback(messages, llm=cap_llm)
            self._log_model_route(self._extract_model_name(response), lane="talk")
            raw_response = response.content if hasattr(response, "content") else str(response)
        except Exception as e:
            logger.error(f"Ошибка вызова LLM: {e}")
            self._publish_chat_turn_failed(
                internal_user_id=internal_uid,
                channel_id=channel_id,
                error=str(e),
            )
            return {
                "text": f"[SOUND: bruh] Что-то сломалось на моей стороне: {e}",
                "sounds": ["bruh"],
                "thoughts": "",
                "raw": "",
            }

        # 6. Парсим CoT (<think> блоки)
        text_no_think, thoughts = self._extract_think_blocks(raw_response)
        text_no_think, micro_plan = self._strip_leading_micro_plan(text_no_think)
        if micro_plan:
            logger.debug("Micro-plan captured | mode=chat | chars=%s", len(micro_plan))
        text_no_think, hidden_final, unclosed_final = self._strip_micro_plan_blocks(text_no_think)
        if hidden_final > 0:
            self._micro_plan_metrics["filtered_final_chars"] += hidden_final
            self._micro_plan_metrics["leak_detected"] += 1
            logger.warning(
                "Micro-plan leak sanitized | mode=chat | hidden_chars=%s | unclosed=%s",
                hidden_final,
                unclosed_final,
            )
        if unclosed_final:
            self._micro_plan_metrics["unclosed_blocks"] += 1

        # 7. Парсим [SOUND: tag]
        clean_text, sounds = self._extract_sound_tags(text_no_think, preserve_line_breaks=lyrics_mode)
        clean_text = self._ensure_nonempty_reply(
            text_no_think, clean_text, preserve_line_breaks=lyrics_mode
        )
        clean_text = await self._retry_short_reply_if_empty(final_messages_used, clean_text)
        clean_text = await self._de_repeat_reply(user_message, clean_text)

        # 8. Обновляем краткосрочную память (та же подпись, что и в HumanMessage)
        self.short_memory.add(
            "user",
            self._format_spoken_user_message(user_message, speaker_label),
        )
        self.short_memory.add("assistant", clean_text)

        # 9. Сохраняем в RAG и логах (chat_log — to_thread; LTM — отдельно)
        metadata = {
            "username": username or "unknown",
            "discord_id": discord_user_id or "",
            "user_id": internal_uid,
        }
        await self._append_turn_to_chat_log(
            user_text=self._format_spoken_user_message(user_message, speaker_label),
            assistant_text=clean_text,
            internal_user_id=internal_uid,
            display_name=username or speaker_label,
            channel_id=channel_id,
            source="chat",
            meta=metadata,
        )
        await self._save_dialog_to_ltm_with_emotion(user_message, clean_text, metadata, speaker_label)

        # 10. Логи
        self._log_thought(thoughts, user_message)
        self._log_chat(user_message, clean_text, metadata)
        self._store_vision_note_if_needed(channel_id, vision_images, thoughts, clean_text)
        self._schedule_async_reflection(
            user_message=user_message,
            assistant_text=clean_text,
            username=username,
            discord_user_id=discord_user_id,
        )
        self._schedule_working_memory_refresh(
            internal_user_id=internal_uid,
            user_message=user_message,
            assistant_text=clean_text,
            speaker_label=speaker_label,
            stm_trimmed=False,
        )
        self._schedule_emotion_diary(
            user_message=user_message,
            assistant_text=clean_text,
            speaker_label=speaker_label,
            username=username,
            discord_user_id=discord_user_id,
        )
        for s in saved_facts:
            self.diary.add_entry(
                text=f"Зафиксировала новый факт в досье: {s}",
                source="memory_update",
                meta={"username": username or "unknown"},
            )

        self._publish_memory_and_chat_events(
            internal_user_id=internal_uid,
            channel_id=channel_id,
            username=username,
            user_message=user_message,
            clean_text=clean_text,
            sounds=sounds,
            metadata=metadata,
        )

        logger.debug(f"Ответ сгенерирован | sounds={sounds} | len={len(clean_text)}")
        if self.micro_planning_enabled:
            m = self._micro_plan_metrics
            logger.debug(
                "Micro-plan metrics | stream_hidden=%s | final_hidden=%s | unclosed=%s | leaks=%s",
                m["filtered_stream_chars"],
                m["filtered_final_chars"],
                m["unclosed_blocks"],
                m["leak_detected"],
            )

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
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        internal_uid = self._resolve_internal_user_id(discord_user_id, username)
        await self._ensure_mcp()

        # 1. Контекст (RAG + досье)
        memories = self.long_memory.search(user_message)
        mentioned = self._detect_mentioned_names(user_message)
        if username:
            person = self.memory_hub.find_person(username, discord_id=discord_user_id)
            if person and person["id"] not in mentioned:
                mentioned.append(person["id"])

        # Эвристика: ручное сохранение фактов
        saved_facts = self._handle_memory_trigger(user_message, mentioned, username)

        people_active, people_others = self._split_people_context_for_prompt(
            mentioned, username, discord_user_id
        )
        diary_ctx = self.memory_hub.diary_recent_text(limit=6)

        # Эвристический веб-поиск
        web_ctx = self._handle_websearch_trigger(user_message)
        tool_ctx = self._collect_tool_context(user_message)

        speaker_label = self._resolve_speaker_label(username, discord_user_id, author_display_name)

        wm_snip = self._read_working_memory_for_prompt(internal_uid)

        has_vis = bool(vision_images)
        last_img_ctx = self._last_image_context_for_prompt(channel_id, vision_images)
        lyrics_mode = LYRICS_REQUEST_MARKER in (user_message or "")

        mcp_cfg_stream = self.config.get("mcp_client") if isinstance(self.config.get("mcp_client"), dict) else {}
        mcp_catalog_s = ""
        if mcp_cfg_stream.get("inject_tool_catalog") and self.mcp_manager:
            ml_s = self.mcp_manager.catalog_lines()
            if ml_s:
                mcp_catalog_s = "\n".join(ml_s)

        brain_native_vis = bool(vision_images) and self._uses_brain_native_vision()
        attached_caption = ""
        if vision_images and not brain_native_vis and self.llm_vision and self.llm_vision is not self.llm_brain:
            try:
                attached_caption = await self._caption_vision_images(
                    user_message, vision_images, speaker_label=speaker_label
                )
            except Exception as e:
                logger.warning("VL caption (stream): ошибка — %s", e)
        elif vision_images and not brain_native_vis and not self.llm_vision:
            logger.warning(
                "Изображения в сообщении (stream), но vision/VL не настроено — ответ только по тексту."
            )

        caption_ok = (attached_caption or "").strip()
        if brain_native_vis:
            talk_vm = None
            has_vis_prompt = False
        else:
            talk_vm = None if (vision_images and self.llm_vision) else vision_images
            has_vis_prompt = bool(vision_images) and not caption_ok and self.llm_vision is None

        brain_sys = self._build_brain_system_prompt(
            extra_memories=memories,
            people_context_active=people_active,
            people_context_mentioned=people_others,
            diary_context=diary_ctx,
            username=speaker_label,
            web_context=web_ctx,
            tool_context=tool_ctx,
            mcp_tools_catalog=mcp_catalog_s,
            last_image_context=last_img_ctx,
            working_memory_context=wm_snip,
        )
        brain_context = ""
        try:
            brain_context = await self._run_brain_tool_phase(
                user_message=user_message,
                speaker_label=speaker_label,
                vision_caption=caption_ok or None,
                vision_images=vision_images if brain_native_vis else None,
                brain_system=brain_sys,
                lyrics_mode=lyrics_mode,
            )
        except Exception as e:
            logger.warning("Brain phase (stream): пропуск сводки — %s", e)

        system_prompt = self._build_system_prompt(
            extra_memories=memories,
            people_context_active=people_active,
            people_context_mentioned=people_others,
            diary_context=diary_ctx,
            username=speaker_label,
            web_context=web_ctx,
            tool_context=tool_ctx,
            has_vision_images=has_vis_prompt,
            last_image_context=last_img_ctx,
            lyrics_mode=lyrics_mode,
            mcp_tools_catalog=mcp_catalog_s,
            brain_router_context=brain_context or "",
            attached_image_caption=caption_ok,
            working_memory_context=wm_snip,
        )

        stream_llm = self.llm_talk
        if lyrics_mode:
            stream_llm = self.llm_talk.bind(
                max_tokens=max(self.reply_max_tokens, self.lyrics_reply_max_tokens)
            )
        if vision_images:
            mode = "brain-native" if brain_native_vis else "caption→brain→talk"
            logger.info(
                "Зрение: %s, изображений=%s | talk_model=%s",
                mode,
                len(vision_images),
                getattr(self, "llm_talk_model", self.llm_model),
            )

        # 2. Сообщения
        messages = [SystemMessage(content=system_prompt)]
        for msg in self.short_memory.get_history():
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(
            self._make_human_turn(user_message, talk_vm, speaker_label=speaker_label)
        )
        messages = self._maybe_append_micro_plan_prefill(
            messages,
            has_vision_images=bool(vision_images) and not brain_native_vis and self.llm_vision is None,
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
                pa, pm = self._shrink_people_sections(people_active, people_others, 500)
                system_prompt = self._build_system_prompt(
                    extra_memories=[],
                    people_context_active=pa,
                    people_context_mentioned=pm,
                    username=speaker_label,
                    web_context="",
                    tool_context="",
                    has_vision_images=has_vis_prompt,
                    last_image_context=last_img_ctx,
                    lyrics_mode=lyrics_mode,
                    mcp_tools_catalog="",
                    brain_router_context=brain_context or "",
                    attached_image_caption=caption_ok,
                    working_memory_context=wm_snip,
                )

                # Повторный запрос
                messages_retry = [SystemMessage(content=system_prompt)]
                for msg in self.short_memory.get_history():
                    if msg["role"] == "user":
                        messages_retry.append(HumanMessage(content=msg["content"]))
                    else:
                        messages_retry.append(AIMessage(content=msg["content"]))
                messages_retry.append(
                    self._make_human_turn(user_message, talk_vm, speaker_label=speaker_label)
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
                        internal_user_id=internal_uid,
                        channel_id=channel_id,
                        error=str(e2),
                    )
                    yield {"type": "error", "text": str(e2)}
                    return
            else:
                logger.error(f"Ошибка стриминга LLM: {e}")
                self._publish_chat_turn_failed(
                    internal_user_id=internal_uid,
                    channel_id=channel_id,
                    error=err_str,
                )
                yield {"type": "error", "text": err_str}
                return

        # 4. Постобработка после завершения стрима
        text_no_think, thoughts = self._extract_think_blocks(raw_response)
        text_no_think, micro_plan = self._strip_leading_micro_plan(text_no_think)
        if micro_plan:
            logger.debug("Micro-plan captured | mode=stream | chars=%s", len(micro_plan))
        text_no_think, hidden_final, unclosed_final = self._strip_micro_plan_blocks(text_no_think)
        if hidden_final > 0:
            self._micro_plan_metrics["filtered_final_chars"] += hidden_final
            self._micro_plan_metrics["leak_detected"] += 1
            logger.warning(
                "Micro-plan leak sanitized | mode=stream | hidden_chars=%s | unclosed=%s",
                hidden_final,
                unclosed_final,
            )
        if unclosed_final:
            self._micro_plan_metrics["unclosed_blocks"] += 1
        clean_text, sounds = self._extract_sound_tags(text_no_think, preserve_line_breaks=lyrics_mode)
        clean_text = self._ensure_nonempty_reply(
            text_no_think, clean_text, preserve_line_breaks=lyrics_mode
        )
        clean_text = await self._retry_short_reply_if_empty(final_messages_used, clean_text)
        clean_text = await self._de_repeat_reply(user_message, clean_text)

        # 5. Память и логи
        if context_exceeded:
            # После автосброса — помечаем что был рестарт (только в логе, не в память)
            logger.info("Успешный ответ после переполнения контекста.")
            
        self.short_memory.add(
            "user",
            self._format_spoken_user_message(user_message, speaker_label),
        )
        self.short_memory.add("assistant", clean_text)

        metadata = {
            "username": username or "unknown",
            "discord_id": discord_user_id or "",
            "user_id": internal_uid,
        }
        await self._append_turn_to_chat_log(
            user_text=self._format_spoken_user_message(user_message, speaker_label),
            assistant_text=clean_text,
            internal_user_id=internal_uid,
            display_name=username or speaker_label,
            channel_id=channel_id,
            source="chat_stream",
            meta=metadata,
        )
        await self._save_dialog_to_ltm_with_emotion(user_message, clean_text, metadata, speaker_label)
        self._log_thought(thoughts, user_message)
        self._log_chat(user_message, clean_text, metadata)
        self._store_vision_note_if_needed(channel_id, vision_images, thoughts, clean_text)
        self._schedule_async_reflection(
            user_message=user_message,
            assistant_text=clean_text,
            username=username,
            discord_user_id=discord_user_id,
        )
        self._schedule_working_memory_refresh(
            internal_user_id=internal_uid,
            user_message=user_message,
            assistant_text=clean_text,
            speaker_label=speaker_label,
            stm_trimmed=context_exceeded,
        )
        self._schedule_emotion_diary(
            user_message=user_message,
            assistant_text=clean_text,
            speaker_label=speaker_label,
            username=username,
            discord_user_id=discord_user_id,
        )
        if self.micro_planning_enabled:
            m = self._micro_plan_metrics
            logger.debug(
                "Micro-plan metrics | stream_hidden=%s | final_hidden=%s | unclosed=%s | leaks=%s",
                m["filtered_stream_chars"],
                m["filtered_final_chars"],
                m["unclosed_blocks"],
                m["leak_detected"],
            )
        for s in saved_facts:
            self.diary.add_entry(
                text=f"Зафиксировала новый факт в досье: {s}",
                source="memory_update",
                meta={"username": username or "unknown"},
            )

        self._publish_memory_and_chat_events(
            internal_user_id=internal_uid,
            channel_id=channel_id,
            username=username,
            user_message=user_message,
            clean_text=clean_text,
            sounds=sounds,
            metadata=metadata,
        )

        logger.debug(f"Стрим завершён | sounds={sounds} | len={len(clean_text)}")

        # 6. Финальный пакет с метаданными
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
        from core.llm_retry import ainvoke_with_rate_limit_backoff

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
