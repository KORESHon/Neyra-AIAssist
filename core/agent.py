"""
core/agent.py — Главный агент Нейры
─────────────────────────────────────
Использует LangChain + Ollama для генерации ответов.
Интегрирован с:
  • ShortTermMemory  — история текущего диалога
  • LongTermMemory   — ChromaDB RAG (прошлые диалоги)
  • PeopleDB         — досье на людей
  • Tools            — инструменты (поиск, время, мониторинг)

Логика ответа:
  1. Ищем похожие диалоги в RAG
  2. Ищем упомянутых людей в PeopleDB
  3. Собираем полный промпт (system + воспоминания + досье + история + запрос)
  4. Передаём LLM с инструментами
  5. Парсим CoT (<think>...</think>), сохраняем в thoughts.log
  6. Парсим [SOUND: tag], убираем из текста
  7. Сохраняем диалог в ChromaDB и chat.log
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

from core.event_bus import (
    CHAT_TURN_COMPLETED,
    CHAT_TURN_FAILED,
    MEMORY_LONG_TERM_WRITE,
    MEMORY_SHORT_TERM_UPDATE,
    CoreEvent,
    EventBus,
)
from core.identity import UnifiedIdentityMapper

logger = logging.getLogger("neyra.agent")
EMPTY_REPLY_PLACEHOLDER = "Затупила на секунду. Повтори коротко, пожалуйста."


class NeyraAgent:
    """Основной агент Нейры."""

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

        from core.llm_profile import merge_llm_tuning_options, resolved_primary_model

        conn = self._llm_connection
        cfg = merge_llm_tuning_options(self.config)
        primary_model = resolved_primary_model(self.config, conn.provider)
        self.context_window = cfg.get("context_window", 16384)
        base_url = conn.base_url
        api_key = conn.api_key
        self.reply_max_tokens = int(cfg.get("reply_max_tokens", cfg.get("max_tokens", 320)))
        self.vision_max_tokens = int(cfg.get("vision_max_tokens", cfg.get("max_tokens", 900)))
        self.reflection_max_tokens = int(cfg.get("reflection_max_tokens", cfg.get("max_tokens", 700)))
        self.reflection_temperature = float(cfg.get("reflection_temperature", cfg.get("temperature", 0.75)))

        if not api_key or api_key == "ollama":
            if conn.provider == "ollama":
                pass
            else:
                logger.error(
                    "API ключ LLM не найден — задай в конфиге llm.api_key / openrouter.api_key "
                    "или переменную окружения для провайдера %s",
                    conn.provider,
                )

        primary_timeout = float(cfg.get("timeout_seconds", cfg.get("primary_timeout_seconds", 120.0)))
        primary_retries = int(cfg.get("max_retries", cfg.get("primary_max_retries", 1)))
        extra_body: dict[str, Any] = {}
        # Опциональные провайдер-специфичные флаги (например, для xAI/Grok).
        if "reasoning_enabled" in cfg:
            extra_body["reasoning_enabled"] = bool(cfg.get("reasoning_enabled"))
        if "include_reasoning" in cfg:
            extra_body["include_reasoning"] = bool(cfg.get("include_reasoning"))

        hdr_primary = dict(conn.default_headers)
        self.llm_primary = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=primary_model,
            temperature=cfg.get("temperature", 0.75),
            top_p=float(cfg.get("top_p", 1.0)),
            presence_penalty=float(cfg.get("presence_penalty", 0.0)),
            frequency_penalty=float(cfg.get("frequency_penalty", 0.0)),
            max_tokens=self.reply_max_tokens,
            streaming=True,
            timeout=primary_timeout,
            max_retries=primary_retries,
            model_kwargs={"extra_body": extra_body} if extra_body else {},
            default_headers=hdr_primary,
        )
        # Жестко режем попытки модели выводить think-теги в основном ответе.
        # Это снижает задержки и убирает кейсы "пустой ответ после очистки".
        self.llm_primary = self.llm_primary.bind(
            stop=["<think>", "</think>", "<thought>", "</thought>", "<redacted_thinking>", "</redacted_thinking>"]
        )
        self.llm = self.llm_primary
        self.llm_model = primary_model
        self.llm_primary_model = primary_model
        self.llm_fallback_model = None
        self.primary_first_token_timeout = float(cfg.get("primary_first_token_timeout_seconds", primary_timeout))
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
        reflection_model = str(
            cfg.get("reflection_model")
            or self.async_reflection_cfg.get("model")
            or primary_model
        ).strip()
        reflection_timeout = float(
            cfg.get(
                "reflection_timeout_seconds",
                self.async_reflection_cfg.get("timeout_seconds", primary_timeout),
            )
        )
        reflection_retries = int(
            cfg.get(
                "reflection_max_retries",
                self.async_reflection_cfg.get("max_retries", primary_retries),
            )
        )
        hdr_reflection = dict(conn.default_headers)
        hdr_reflection["X-Title"] = "Neyra Reflection"
        self.llm_reflection = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=reflection_model,
            temperature=self.reflection_temperature,
            max_tokens=self.reflection_max_tokens,
            streaming=False,
            timeout=reflection_timeout,
            max_retries=reflection_retries,
            default_headers=hdr_reflection,
        )
        self.llm_reflection_model = reflection_model
        self.llm_think = None
        logger.info(
            "Бэкенд LLM: %s | модель: %s | timeout=%ss retries=%s | max_ctx: %s",
            conn.provider,
            primary_model,
            primary_timeout,
            primary_retries,
            self.context_window,
        )
        logger.info(
            "LLM token budgets | reply=%s | vision=%s | reflection=%s | async_reflection=%s",
            self.reply_max_tokens,
            self.vision_max_tokens,
            self.reflection_max_tokens,
            int(self.async_reflection_cfg.get("max_tokens", 500)),
        )
        logger.info(
            "LLM models | live=%s | reflection=%s | async_reflection=%s",
            primary_model,
            reflection_model,
            str(self.async_reflection_cfg.get("model") or ""),
        )
        if self.async_reflection_enabled:
            think_model = str(self.async_reflection_cfg.get("model") or "").strip()
            if think_model:
                hdr_think = dict(conn.default_headers)
                hdr_think["X-Title"] = "Neyra Async Reflection"
                self.llm_think = ChatOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    model=think_model,
                    temperature=float(self.async_reflection_cfg.get("temperature", 0.6)),
                    max_tokens=int(self.async_reflection_cfg.get("max_tokens", 500)),
                    streaming=False,
                    timeout=float(self.async_reflection_cfg.get("timeout_seconds", 60)),
                    max_retries=int(self.async_reflection_cfg.get("max_retries", 1)),
                    default_headers=hdr_think,
                )
                logger.info("Async reflection включен | think_model=%s", think_model)
            else:
                logger.warning("async_reflection.enabled=true, но не задан openrouter.async_reflection.model")

        # Без bind_tools: Qwen через OpenRouter нормально не делает tool-calls; инструменты — триггеры в коде
        self.llm_with_tools = self.llm
        self.llm_capabilities = dict(conn.capabilities)

        vis = self.config.get("vision") or {}
        self.llm_vision = None
        if vis.get("enabled"):
            if vis.get("use_main_model_for_vision"):
                # Для vision используем ту же основную модель.
                self.llm_vision = self.llm_primary
                logger.info(
                    "Зрение: unified — та же модель что и текст (%s). Должна быть VL-capable модель.",
                    primary_model,
                )
            elif str(vis.get("model") or "").strip():
                vmodel = str(vis["model"]).strip()
                hdr_vision = dict(conn.default_headers)
                hdr_vision["X-Title"] = "Neyra AI Vision"
                self.llm_vision = ChatOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    model=vmodel,
                    temperature=cfg.get("temperature", 0.75),
                    max_tokens=self.vision_max_tokens,
                    streaming=True,
                    timeout=180,
                    default_headers=hdr_vision,
                )
                logger.info("Зрение: отдельная VL-модель (%s) — %s", conn.provider, vmodel)
            else:
                logger.warning(
                    "vision.enabled, но нет vision.model и use_main_model_for_vision=false — VL выключен."
                )

    def _setup_memory(self):
        """Инициализирует все модули памяти."""
        from core.memory import LongTermMemory, NeyraDiary, PeopleDB, ShortTermMemory

        self.short_memory = ShortTermMemory(max_messages=10)
        self.long_memory = LongTermMemory(self.config)
        self.people_db = PeopleDB(self.config)
        self.diary = NeyraDiary(self.config)

        # Не блокируем старт бота тяжёлой загрузкой embedder'а:
        # RAG поднимется в фоне, а при первом запросе есть ленивый fallback.
        mem_cfg = self.config.get("memory", {}) or {}
        if bool(mem_cfg.get("rag_init_in_background", True)):
            logger.info("Инициализирую долгосрочную память в фоне...")
            self.long_memory.initialize_async()
        else:
            logger.info("Инициализирую долгосрочную память...")
            self.long_memory.initialize()

        # Создаём начальные досье если их нет
        self._init_people_db()

    def _setup_tools(self):
        """Инициализирует инструменты (вызываются вручную, не через bind_tools)."""
        from core.tools import ALL_TOOLS, init_tools

        init_tools(self.long_memory, self.people_db, self.config.get("assistant") or {})
        self.tools = {t.name: t for t in ALL_TOOLS}
        logger.info(f"Tools готовы: {list(self.tools.keys())}")

    def _setup_logs(self):
        """Создаёт директории и файлы для логов."""
        mem_cfg = self.config.get("memory", {})
        log_cfg = self.config.get("logging", {})

        self.thoughts_log_path = Path(mem_cfg.get("thoughts_log", "./memory/thoughts.log"))
        self.chat_log_path = Path(log_cfg.get("chat_log", "./logs/chat.log"))

        self.thoughts_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.chat_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _init_people_db(self):
        """Создаёт базовые досье если папка пустая."""
        if len(list(self.people_db.db_dir.glob("*.json"))) > 0:
            return  # Уже есть файлы

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
                    "traits": "клички принимает и не обижается",
                    "notes": "В дискорде не сидит."
                },
                "dynamic_facts": [],
            },
        ]

        import json
        for person in people:
            person.setdefault("last_seen", None)
            path = self.people_db.db_dir / f"{person['id']}.json"
            path.write_text(
                json.dumps(person, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

        self.people_db._load_all()
        logger.info(f"Создано {len(people)} начальных досье")

    # ─── Системный промпт ──────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        extra_memories: list[str] = None,
        people_context: str = "",
        diary_context: str = "",
        username: str = None,
        web_context: str = "",
        tool_context: str = "",
        has_vision_images: bool = False,
        last_image_context: Optional[str] = None,
    ) -> str:
        """Собирает финальный системный промпт с контекстом."""
        base = self.config["assistant"]["system_prompt"]

        # Короткая нейтральная системная ремарка о среде.
        from core.llm_profile import is_local_openai_compatible_provider

        if is_local_openai_compatible_provider(self.backend):
            hw_note = "\n[СИСТЕМНАЯ ИНФОРМАЦИЯ: Работаешь через локальный/self-host OpenAI-compatible LLM endpoint.]"
        else:
            hw_note = "\n[СИСТЕМНАЯ ИНФОРМАЦИЯ: Работаешь через облачный LLM API (OpenAI-compatible).]"

        from datetime import datetime
        now = datetime.now()
        time_context = f"\n\n[СИСТЕМНАЯ ВАЖНАЯ ИНФОРМАЦИЯ]\nТекущее время и дата: {now.strftime('%Y-%m-%d %H:%M:%S')}"
        if username:
            time_context += (
                f"\nТЕКУЩИЙ СОБЕСЕДНИК: {username}. "
                "Ориентируйся на это имя как на основной контекст текущего диалога."
            )

        sections = [base + hw_note + time_context]
        sections.append(
            "\n[КРИТИЧЕСКОЕ ПРАВИЛО ОТВЕТА]\n"
            "Запрещено выводить теги/блоки внутреннего мышления: "
            "<think>, <thought>, <redacted_thinking> и любые их варианты. "
            "Отвечай сразу готовым текстом для пользователя."
        )
        sections.append(
            "\n[АНТИ-ПОВТОР И РЕЛЕВАНТНОСТЬ]\n"
            "Сначала ответь ПО СМЫСЛУ текущего сообщения пользователя. "
            "Токсичность/локальные мемы/подколы используй как приправу, а не как основной контент. "
            "Не повторяй дословно свои последние фразы из истории чата."
        )
        if self.micro_planning_enabled:
            if self.micro_plan_mode == "anchor":
                sections.append(
                    "\n[МИКРО-ПЛАНИРОВАНИЕ]\n"
                    "Перед финальным ответом сформируй короткий внутренний план (до 8 слов) "
                    "в anchor-формате, затем сам ответ пользователю. "
                    "Не используй markdown.\n"
                    "Шаблон (ОБЯЗАТЕЛЬНЫЙ формат):\n"
                    f"Пользователь: Ало, как дела?\n"
                    f"Нейра: {self.micro_plan_anchor_prefix} коротко поприветствовать. "
                    f"{self.micro_plan_anchor_reply} Привет! Всё нормально, как ты?\n"
                    f"Если не можешь соблюсти формат с {self.micro_plan_anchor_prefix} и "
                    f"{self.micro_plan_anchor_reply}, не пиши план вообще и сразу отвечай пользователю."
                )
            else:
                sections.append(
                    "\n[МИКРО-ПЛАНИРОВАНИЕ]\n"
                    f"Перед основным текстом добавь КОРОТКИЙ внутренний план в тегах "
                    f"{self.micro_plan_start}...{self.micro_plan_end} (до 8 слов), "
                    "после него сразу дай обычный ответ для пользователя. "
                    "Не используй markdown.\n"
                    "Шаблон (ОБЯЗАТЕЛЬНЫЙ формат):\n"
                    f"Пользователь: Ало, как дела?\n"
                    f"Нейра: {self.micro_plan_start}поприветствовать и коротко ответить{self.micro_plan_end} "
                    "Привет! Всё нормально, как ты?\n"
                    f"Если не можешь соблюсти формат {self.micro_plan_start}...{self.micro_plan_end}, "
                    "не пиши план вообще и сразу давай обычный ответ."
                )

        # Досье упомянутых людей
        if people_context:
            sections.append(f"\n# АКТУАЛЬНОЕ ДОСЬЕ (из базы):\n{people_context}")

        if diary_context:
            sections.append(f"\n# ЛИЧНЫЙ ДНЕВНИК НЕЙРЫ (последние заметки):\n{diary_context}")

        if web_context:
            sections.append(f"\n# ИНФОРМАЦИЯ ИЗ ИНТЕРНЕТА ПО ЗАПРОСУ ПОЛЬЗОВАТЕЛЯ:\n{web_context}\n(Используй эти актуальные данные для ответа на вопрос пользователя)")

        if tool_context:
            sections.append(
                f"\n# РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ (уже посчитано кодом, не выдумывай другое):\n{tool_context}"
            )

        # Воспоминания из RAG
        if extra_memories:
            memories_text = "\n".join(f"- {m[:300]}" for m in extra_memories)
            sections.append(f"\n# ВОСПОМИНАНИЯ ИЗ ПРОШЛЫХ РАЗГОВОРОВ:\n{memories_text}")

        if has_vision_images:
            sections.append(
                "\n[ЗРЕНИЕ — ПРИОРИТЕТ НАД БРЕДОМ И ПОДКОЛАМИ]\n"
                "К этому сообщению прикреплены изображения; тебе в запрос переданы пиксели через VL-модель.\n"
                "СНАЧАЛА по делу: 1–3 коротких предложения — что на картинке (интерфейс, люди, текст на скрине — "
                "перечисли читаемое дословно или очень близко). Опирайся только на видимое, не выдумывай.\n"
                "ЗАПРЕЩЕНО вместо описания отвечать шаблонами вроде «ничего не вижу», «почти ничего», "
                "«смотри нормально», «слепой», «криворукий», «что за хрень на картинке» — это будет ложь: изображение передано.\n"
                "После обязательного описания можешь одной фразой в своём тоне, без Markdown."
            )
        elif last_image_context:
            sections.append(
                "\n[ПОСЛЕДНИЙ СКРИН В ЭТОМ КАНАЛЕ — НОВОГО ВЛОЖЕНИЯ НЕТ]\n"
                "Ниже сжатая заметка с прошлого VL-хода (внутренний разбор, либо конспект ответа, если монолога не было). "
                "Если юзер переспрашивает про ту картинку — опирайся на это; для новых деталей по пикселям попроси скинуть скрин снова.\n"
                f"{last_image_context}"
            )

        return "\n".join(sections)

    def _make_vision_memory_note(self, thoughts: str, clean_text: str) -> str:
        """Текст для «памяти последнего скрина»: приоритет — CoT/think из ответа VL."""
        vis = self.config.get("vision") or {}
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
        vis_cfg = self.config.get("vision") or {}
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
        vis = self.config.get("vision") or {}
        if not vis.get("remember_last_image", True):
            return
        note = self._make_vision_memory_note(thoughts, clean_text)
        if note:
            self._last_vision_note_by_channel[str(channel_id)] = note
            logger.debug("Зрение: заметка по каналу %s (%s симв.)", channel_id, len(note))

    def _make_human_turn(
        self,
        user_message: str,
        vision_images: Optional[list[tuple[str, str]]] = None,
    ):
        """HumanMessage: текст или мультимодальный контент (mime, base64) для VL."""
        from langchain_core.messages import HumanMessage

        use_vl = bool(vision_images) and self.llm_vision is not None
        if vision_images and not self.llm_vision:
            logger.warning(
                "Изображения в сообщении, но llm_vision нет: vision.enabled, vision.model или use_main_model_for_vision "
                "(или основная модель без VL)."
            )
        if use_vl:
            text = (user_message or "").strip() or "Что на изображении? Коротко по-русски."
            parts: list[dict] = [{"type": "text", "text": text}]
            for mime, b64 in vision_images:
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime};base64,{b64}",
                            "detail": "auto",
                        },
                    }
                )
            return HumanMessage(content=parts)
        return HumanMessage(content=user_message)

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

    def _log_model_route(self, used_model: Optional[str], *, vision: bool = False) -> None:
        if not used_model:
            return
        primary = str(getattr(self, "llm_primary_model", "") or "")
        fallback = str(getattr(self, "llm_fallback_model", "") or "")
        route = "primary"
        if fallback and fallback in used_model:
            route = "fallback"
        kind = "vision" if vision else "text"
        logger.info("LLM route | kind=%s | route=%s | model=%s", kind, route, used_model)

    async def _run_async_reflection(
        self,
        user_message: str,
        assistant_text: str,
        username: Optional[str],
        discord_user_id: Optional[str],
    ) -> None:
        if not self.async_reflection_enabled or not self.llm_think:
            return
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

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
            resp = await self.llm_think.ainvoke(
                [SystemMessage(content=sys_prompt), HumanMessage(content=human)]
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
        if not self.async_reflection_enabled or not self.llm_think:
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

    async def _ainvoke_text_with_fallback(self, messages: list[Any]):
        """Обычный нестриминговый вызов (одна модель)."""
        return await self.llm_primary.ainvoke(messages)

    async def _astream_text_with_fallback(self, messages: list[Any]):
        """Стриминговый вызов live-модели с guard по first-token timeout и 1 ретраем."""
        first_timeout = max(0.1, float(getattr(self, "primary_first_token_timeout", 8.0)))
        attempts = 2
        last_err: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            stream = self.llm_primary.astream(messages)
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

    def _extract_sound_tags(self, text: str) -> tuple[str, list[str]]:
        """Вырезает [SOUND: tag] из текста, возвращает (чистый текст, список тегов)."""
        pattern = r"\[SOUND:\s*(\w+)\]"
        tags = re.findall(pattern, text)
        clean = re.sub(pattern, "", text).strip()
        
        # Жестко вырезаем все остальные [Roleplay] и [Действия] скобки, если модель опять галлюцинирует
        clean = re.sub(r"\[[^\]]*\]", "", clean)
        
        # Агрессивно вырезаем ЛЮБЫЕ действия в звездочках *Злобно хихикает*
        clean = re.sub(r"\*[^\*]{2,150}\*", "", clean)
        
        # Агрессивно вырезаем действия в скобках (закатывает глаза)
        # Ищем скобки, в которых есть хотя бы 1 слово на кириллице
        clean = re.sub(r"\([^\)]*[А-Яа-яЁё][^\)]*\)", "", clean)

        # Вырезаем спам из японских смайликов и спецсимволов: ~(>_<)~, (o_O), и тд
        # Удаляем любые конструкции начинающиеся с ~ и заканчивающиеся на ~
        clean = re.sub(r"~[^a-zA-Zа-яА-ЯёЁ]{1,20}~", "", clean)
        # Убираем кавычки, если модель случайно обернула всю фразу в "Текст"
        if clean.startswith('"') and clean.endswith('"'):
            clean = clean[1:-1]

        # Убираем двойные пробелы, оставшиеся после вырезания
        clean = re.sub(r"\s+", " ", clean).strip()
        clean = clean.replace('""', '"').replace("''", "'")
        
        return clean, tags

    def _extract_think_blocks(self, text: str) -> tuple[str, str]:
        """Вырезает <think>/<thought> блоки (модель использует оба варианта)."""
        # Захватываем <think>...</think> и <thought>...</thought>
        pattern = r"<(?:redacted_thinking|think|thought)>(.*?)</(?:redacted_thinking|think|thought)>"
        thoughts = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        clean = re.sub(pattern, "", text, flags=re.DOTALL | re.IGNORECASE)

        # Убираем незакрытые хвосты типа </thought> или </think> в конце
        clean = re.sub(
            r"</?(?:redacted_thinking|think|thought)>",
            "",
            clean,
            flags=re.IGNORECASE,
        )

        # Чистим мусор в начале: ". Текст" → "Текст"
        clean = clean.strip()
        clean = re.sub(r"^[\s.,;:\-–—]+", "", clean).strip()

        return clean, "\n---\n".join(thoughts)

    def _ensure_nonempty_reply(self, text_no_think: str, clean_text: str) -> str:
        """
        Гарантирует, что после пост-очистки ответ не станет пустым.
        Иногда модель уходит в служебные блоки/скобки и после фильтров ничего не остаётся.
        """
        c = (clean_text or "").strip()
        if c:
            return c
        # Мягкий salvage: убираем только SOUND-теги и лишние пробелы.
        t = re.sub(r"\[SOUND:\s*\w+\]", "", (text_no_think or ""), flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip()
        if t:
            return t
        logger.warning("Пустой ответ после очистки: fallback-фраза")
        return EMPTY_REPLY_PLACEHOLDER

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
            resp = await self.llm_primary.ainvoke(retry_messages)
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
        src = (text or "").strip()
        if not self.micro_planning_enabled:
            return src, ""
        if not src.startswith(self.micro_plan_start):
            return src, ""
        end_idx = src.find(self.micro_plan_end)
        if end_idx < 0:
            return src, ""
        plan = src[len(self.micro_plan_start):end_idx].strip()
        rest = src[end_idx + len(self.micro_plan_end):].strip()
        return rest, plan

    def _init_micro_plan_state(self) -> dict:
        return {
            "in_plan": False,
            "start_idx": 0,
            "end_idx": 0,
            "hidden_chars": 0,
            "anchor_decided": False,
            "anchor_mode": False,
            "lead_buffer": "",
            "say_idx": 0,
        }

    def _filter_micro_plan_token(self, token: str, st: dict) -> str:
        """State-machine фильтр: скрывает содержимое между start/end тегами без буферизации всего ответа."""
        if not self.micro_planning_enabled:
            return token
        if self.micro_plan_mode == "anchor":
            return self._filter_micro_plan_token_anchor(token, st)
        start = self.micro_plan_start
        end = self.micro_plan_end
        if not start or not end:
            return token
        out: list[str] = []
        i = 0
        while i < len(token):
            ch = token[i]
            if not st["in_plan"]:
                sidx = st["start_idx"]
                if ch == start[sidx]:
                    st["start_idx"] = sidx + 1
                    i += 1
                    if st["start_idx"] >= len(start):
                        st["in_plan"] = True
                        st["start_idx"] = 0
                    continue
                if st["start_idx"] > 0:
                    out.append(start[: st["start_idx"]])
                    st["start_idx"] = 0
                    continue  # re-check current char
                out.append(ch)
                i += 1
            else:
                eidx = st["end_idx"]
                if ch == end[eidx]:
                    st["end_idx"] = eidx + 1
                    i += 1
                    if st["end_idx"] >= len(end):
                        st["in_plan"] = False
                        st["end_idx"] = 0
                    continue
                if st["end_idx"] > 0:
                    st["end_idx"] = 0
                    continue  # re-check current char
                st["hidden_chars"] += 1
                i += 1  # скрываем символ внутри плана
        return "".join(out)

    def _filter_micro_plan_token_anchor(self, token: str, st: dict) -> str:
        plan_anchor = self.micro_plan_anchor_prefix
        say_anchor = self.micro_plan_anchor_reply
        if not plan_anchor or not say_anchor:
            return token

        # Короткое "окно решения": если ответ начинается с PLAN:, скрываем до SAY:.
        if not st["anchor_decided"]:
            st["lead_buffer"] += token
            probe = st["lead_buffer"].lstrip()
            if probe.startswith(plan_anchor):
                st["anchor_decided"] = True
                st["anchor_mode"] = True
                st["hidden_chars"] += len(st["lead_buffer"])
                st["lead_buffer"] = ""
                return ""
            if len(probe) >= len(plan_anchor) or not plan_anchor.startswith(probe):
                st["anchor_decided"] = True
                out = st["lead_buffer"]
                st["lead_buffer"] = ""
                return out
            return ""

        if not st["anchor_mode"]:
            return token

        out: list[str] = []
        i = 0
        while i < len(token):
            ch = token[i]
            sidx = st["say_idx"]
            if ch == say_anchor[sidx]:
                st["say_idx"] = sidx + 1
                st["hidden_chars"] += 1
                i += 1
                if st["say_idx"] >= len(say_anchor):
                    st["anchor_mode"] = False
                    st["say_idx"] = 0
                continue
            if st["say_idx"] > 0:
                st["hidden_chars"] += st["say_idx"]
                st["say_idx"] = 0
                continue
            st["hidden_chars"] += 1
            i += 1
        return "".join(out)

    def _finalize_micro_plan_state(self, st: dict) -> str:
        if not self.micro_planning_enabled:
            return ""
        if st.get("hidden_chars", 0) > 0:
            self._micro_plan_metrics["filtered_stream_chars"] += int(st["hidden_chars"])
        if self.micro_plan_mode == "anchor":
            if not st.get("anchor_decided"):
                tail = st.get("lead_buffer", "")
                st["lead_buffer"] = ""
                return tail
            if st.get("anchor_mode"):
                self._micro_plan_metrics["unclosed_blocks"] += 1
            return ""
        if not st.get("in_plan") and st.get("start_idx", 0) > 0:
            tail = self.micro_plan_start[: st["start_idx"]]
            st["start_idx"] = 0
            return tail
        if st.get("in_plan"):
            self._micro_plan_metrics["unclosed_blocks"] += 1
        return ""

    def _strip_micro_plan_blocks(self, text: str) -> tuple[str, int, bool]:
        """Финальный fail-safe: вырезает все блоки start...end и обрезает незакрытый хвост."""
        if not self.micro_planning_enabled:
            return (text or ""), 0, False
        if self.micro_plan_mode == "anchor":
            return self._strip_micro_plan_anchor(text)
        src = text or ""
        start = self.micro_plan_start
        end = self.micro_plan_end
        if not start or not end or start not in src:
            return src, 0, False

        out: list[str] = []
        i = 0
        hidden = 0
        unclosed = False
        while i < len(src):
            s = src.find(start, i)
            if s < 0:
                out.append(src[i:])
                break
            out.append(src[i:s])
            e = src.find(end, s + len(start))
            if e < 0:
                hidden += len(src) - s
                unclosed = True
                break
            hidden += e + len(end) - s
            i = e + len(end)
        return "".join(out).strip(), hidden, unclosed

    def _strip_micro_plan_anchor(self, text: str) -> tuple[str, int, bool]:
        src = (text or "").strip()
        plan_anchor = self.micro_plan_anchor_prefix
        say_anchor = self.micro_plan_anchor_reply
        if not plan_anchor or not say_anchor:
            return src, 0, False
        if not src.startswith(plan_anchor):
            return src, 0, False
        say_idx = src.find(say_anchor, len(plan_anchor))
        if say_idx < 0:
            return "", len(src), True
        hidden = say_idx + len(say_anchor)
        rest = src[say_idx + len(say_anchor):].strip()
        return rest, hidden, False

    def _maybe_append_micro_plan_prefill(
        self,
        messages: list[Any],
        *,
        has_vision_images: bool,
    ) -> list[Any]:
        if not self.micro_planning_enabled or not self.micro_plan_prefill_enabled or has_vision_images:
            return messages
        try:
            from langchain_core.messages import AIMessage
            prefill = self.micro_plan_start if self.micro_plan_mode != "anchor" else f"{self.micro_plan_anchor_prefix} "
            return [*messages, AIMessage(content=prefill)]
        except Exception:
            return messages

    async def _de_repeat_reply(self, user_message: str, clean_text: str) -> str:
        """
        Если новый ответ почти дублирует предыдущий ответ ассистента,
        делаем быструю переформулировку, чтобы не зацикливаться.
        """
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
            rewrite_llm = self.llm_primary.bind(max_tokens=90, temperature=0.9)
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
        import re
        text_lower = text.lower()
        name_map = self.people_db.get_all_names_map()
        found = []
        for name_lower, pid in name_map.items():
            if pid in found:
                continue
            
            # Точное совпадение (для коротких имен или английских ников)
            if name_lower in text_lower:
                found.append(pid)
                continue
                
            # Совпадение с учетом падежей (обрезаем последнюю букву и ищем как корень слова)
            if len(name_lower) >= 4:
                stem = name_lower[:-1]
                # Ищем \bкорень + 0-2 буквы окончания\b
                if re.search(r'\b' + re.escape(stem) + r'[а-яa-z]{0,2}\b', text_lower):
                    found.append(pid)
                    
        return found

    # ─── Инструменты — ручной вызов ────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, **kwargs) -> str:
        """Выполняет инструмент по имени (для команд / расширений)."""
        t = self.tools.get(tool_name)
        if not t:
            return f"Инструмент '{tool_name}' не найден"
        try:
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
            author_p = self.people_db.find(username) if username else None
            
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
        return self.diary.recent_text(limit=limit) or "Дневник пока пуст."

    def _handle_websearch_trigger(self, text: str) -> str:
        """Эвристический веб-поиск: актуальные темы/новости/фактуальные вопросы без явных триггеров."""
        text_lower = text.lower()
        
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
        self.event_bus.publish(
            CoreEvent(
                MEMORY_SHORT_TERM_UPDATE,
                "core.agent",
                {
                    "user_id": internal_user_id,
                    "channel_id": channel_id,
                    "short_memory_messages": len(self.short_memory),
                },
            )
        )
        self.event_bus.publish(
            CoreEvent(
                MEMORY_LONG_TERM_WRITE,
                "core.agent",
                {
                    "user_id": internal_user_id,
                    "username": metadata.get("username"),
                    "discord_id": metadata.get("discord_id"),
                    "rag_enabled": self.long_memory.rag_enabled,
                },
            )
        )
        self.event_bus.publish(
            CoreEvent(
                CHAT_TURN_COMPLETED,
                "core.agent",
                {
                    "user_id": internal_user_id,
                    "channel_id": channel_id,
                    "username": username,
                    "user_chars": len(user_message or ""),
                    "assistant_chars": len(clean_text or ""),
                    "sounds": list(sounds) if sounds else [],
                },
            )
        )

    def _publish_chat_turn_failed(
        self,
        *,
        internal_user_id: str,
        channel_id: Optional[str],
        error: str,
    ) -> None:
        self.event_bus.publish(
            CoreEvent(
                CHAT_TURN_FAILED,
                "core.agent",
                {
                    "user_id": internal_user_id,
                    "channel_id": channel_id,
                    "error": error[:2000],
                },
            )
        )

    async def chat(
        self,
        user_message: str,
        username: Optional[str] = None,
        discord_user_id: Optional[str] = None,
        vision_images: Optional[list[tuple[str, str]]] = None,
        channel_id: Optional[str] = None,
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

        # 1. Ищем воспоминания в RAG
        memories = self.long_memory.search(user_message)

        # 2. Ищем упомянутых людей
        mentioned = self._detect_mentioned_names(user_message)
        if username:
            person = self.people_db.find(username, discord_id=discord_user_id)
            if person and person["id"] not in mentioned:
                mentioned.append(person["id"])

        # Эвристика: ручное сохранение фактов
        saved_facts = self._handle_memory_trigger(user_message, mentioned, username)

        people_ctx = ""
        if mentioned:
            summaries = [self.people_db.get_summary(pid) for pid in mentioned]
            people_ctx = "\n\n".join(s for s in summaries if s)
        diary_ctx = self.diary.recent_text(limit=6)

        # Эвристический веб-поиск
        web_ctx = self._handle_websearch_trigger(user_message)
        tool_ctx = self._collect_tool_context(user_message)

        # Разрешаем настоящее имя спикера
        speaker_name = username
        if username:
            person = self.people_db.find(username, discord_id=discord_user_id)
            if person:
                speaker_name = f"{person['names'][0]} (Discord-ник: {username})"

        has_vis = bool(vision_images)
        last_img_ctx = self._last_image_context_for_prompt(channel_id, vision_images)
        # 3. Системный промпт
        system_prompt = self._build_system_prompt(
            extra_memories=memories,
            people_context=people_ctx,
            diary_context=diary_ctx,
            username=speaker_name,
            web_context=web_ctx,
            tool_context=tool_ctx,
            has_vision_images=has_vis,
            last_image_context=last_img_ctx,
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
        messages.append(self._make_human_turn(user_message, vision_images))
        messages = self._maybe_append_micro_plan_prefill(
            messages,
            has_vision_images=bool(vision_images),
        )
        final_messages_used = messages

        llm_use = self._stream_llm(vision_images)
        # 5. Вызов LLM
        try:
            if vision_images:
                response = await llm_use.ainvoke(messages)
            else:
                response = await self._ainvoke_text_with_fallback(messages)
            self._log_model_route(self._extract_model_name(response), vision=bool(vision_images))
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
        clean_text, sounds = self._extract_sound_tags(text_no_think)
        clean_text = self._ensure_nonempty_reply(text_no_think, clean_text)
        clean_text = await self._retry_short_reply_if_empty(final_messages_used, clean_text)
        clean_text = await self._de_repeat_reply(user_message, clean_text)

        # 8. Обновляем краткосрочную память
        # Добавляем префикс с именем, чтобы модель различала разных людей
        display_name = username or "user"
        self.short_memory.add("user", f"[от: {display_name}] {user_message}")
        self.short_memory.add("assistant", clean_text)

        # 9. Сохраняем в RAG и логах (не ждём — fire and forget)
        metadata = {
            "username": username or "unknown",
            "discord_id": discord_user_id or "",
            "user_id": internal_uid,
        }
        self.long_memory.save(user_message, clean_text, metadata)

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

        # 1. Контекст (RAG + досье)
        memories = self.long_memory.search(user_message)
        mentioned = self._detect_mentioned_names(user_message)
        if username:
            person = self.people_db.find(username, discord_id=discord_user_id)
            if person and person["id"] not in mentioned:
                mentioned.append(person["id"])

        # Эвристика: ручное сохранение фактов
        saved_facts = self._handle_memory_trigger(user_message, mentioned, username)

        people_ctx = ""
        if mentioned:
            summaries = [self.people_db.get_summary(pid) for pid in mentioned]
            people_ctx = "\n\n".join(s for s in summaries if s)
        diary_ctx = self.diary.recent_text(limit=6)

        # Эвристический веб-поиск
        web_ctx = self._handle_websearch_trigger(user_message)
        tool_ctx = self._collect_tool_context(user_message)

        speaker_name = username
        if username:
            person = self.people_db.find(username, discord_id=discord_user_id)
            if person:
                speaker_name = f"{person['names'][0]} (Discord-ник: {username})"

        has_vis = bool(vision_images)
        last_img_ctx = self._last_image_context_for_prompt(channel_id, vision_images)
        system_prompt = self._build_system_prompt(
            extra_memories=memories,
            people_context=people_ctx,
            diary_context=diary_ctx,
            username=speaker_name,
            web_context=web_ctx,
            tool_context=tool_ctx,
            has_vision_images=has_vis,
            last_image_context=last_img_ctx,
        )

        llm_use = self._stream_llm(vision_images)
        if vision_images:
            vis_cfg = self.config.get("vision") or {}
            vlog = (
                f"{self.llm_model} (unified)"
                if vis_cfg.get("use_main_model_for_vision")
                else (vis_cfg.get("model") or "")
            )
            logger.info(
                "Зрение: VL-ход, изображений=%s, модель=%s",
                len(vision_images),
                vlog,
            )

        # 2. Сообщения
        messages = [SystemMessage(content=system_prompt)]
        for msg in self.short_memory.get_history():
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
        messages.append(self._make_human_turn(user_message, vision_images))
        messages = self._maybe_append_micro_plan_prefill(
            messages,
            has_vision_images=bool(vision_images),
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
            if vision_images:
                stream_iter = llm_use.astream(messages)
            else:
                stream_iter = self._astream_text_with_fallback(messages)
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
            self._log_model_route(used_model_name, vision=bool(vision_images))
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
                system_prompt = self._build_system_prompt(
                    extra_memories=[],
                    people_context=people_ctx[:500],
                    username=speaker_name,
                    web_context="",
                    tool_context="",
                    has_vision_images=has_vis,
                    last_image_context=last_img_ctx,
                )

                # Повторный запрос
                messages_retry = [SystemMessage(content=system_prompt)]
                for msg in self.short_memory.get_history():
                    if msg["role"] == "user":
                        messages_retry.append(HumanMessage(content=msg["content"]))
                    else:
                        messages_retry.append(AIMessage(content=msg["content"]))
                messages_retry.append(self._make_human_turn(user_message, vision_images))
                final_messages_used = messages_retry

                try:
                    if vision_images:
                        retry_iter = llm_use.astream(messages_retry)
                    else:
                        retry_iter = self._astream_text_with_fallback(messages_retry)
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
                    self._log_model_route(used_model_name, vision=bool(vision_images))
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
        clean_text, sounds = self._extract_sound_tags(text_no_think)
        clean_text = self._ensure_nonempty_reply(text_no_think, clean_text)
        clean_text = await self._retry_short_reply_if_empty(final_messages_used, clean_text)
        clean_text = await self._de_repeat_reply(user_message, clean_text)

        # 5. Память и логи
        if context_exceeded:
            # После автосброса — помечаем что был рестарт (только в логе, не в память)
            logger.info("Успешный ответ после переполнения контекста.")
            
        display_name = username or "user"
        self.short_memory.add("user", f"[от: {display_name}] {user_message}")
        self.short_memory.add("assistant", clean_text)

        metadata = {
            "username": username or "unknown",
            "discord_id": discord_user_id or "",
            "user_id": internal_uid,
        }
        self.long_memory.save(user_message, clean_text, metadata)
        self._log_thought(thoughts, user_message)
        self._log_chat(user_message, clean_text, metadata)
        self._store_vision_note_if_needed(channel_id, vision_images, thoughts, clean_text)
        self._schedule_async_reflection(
            user_message=user_message,
            assistant_text=clean_text,
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
        return {
            "mode": self.mode,
            "llm_provider": self.backend,
            "model": self.llm_model,
            "short_memory_size": len(self.short_memory),
            "long_memory_records": self.long_memory.count(),
            "people_db_records": len(self.people_db._cache),
            "tools_count": len(self.tools),
            "event_bus": self.event_bus.handler_counts(),
        }
