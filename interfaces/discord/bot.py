"""
Discord-интерфейс Нейры: диалог в тексте/картинках (без STT/TTS) и музыка (Lavalink).

Задача:
- принимать сообщения и вложения;
- стримить ответы агента;
- обрабатывать музыкальные интенты и эмбеды очереди.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import json
import logging
import os
from datetime import datetime, timezone
import re
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice

from core.event_bus import (
    MUSIC_CLEAR,
    MUSIC_PAUSE,
    MUSIC_PLAY,
    MUSIC_QUEUE,
    MUSIC_RESUME,
    MUSIC_RESULT,
    MUSIC_SKIP,
    MUSIC_STOP,
    NOTIFY_DISCORD_MESSAGE_SENT,
    CoreEvent,
)

if TYPE_CHECKING:
    from core.agent import NeyraAgent
    from core.reflection import ReflectionEngine

logger = logging.getLogger("neyra.discord")

MAX_MSG_LEN = 1900
THINKING_DOT = "▌"
QUEUE_PAGE_SIZE = 10
# Discord embed field value limit; keep headroom for ellipsis
EMBED_FIELD_SAFE = 1000

COL_BRAND = 0x5865F2
COL_OK = 0x57F287
COL_ERR = 0xED4245
COL_WARN = 0xFEE75C


def _clip_field(text: str, limit: int = EMBED_FIELD_SAFE) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t or "—"
    return t[: max(0, limit - 1)] + "…"


def _normalize_music_handler_result(result: dict[str, Any]) -> dict[str, Any]:
    """Event path uses payload.result; invoke_plugin returns top-level result."""
    pl = result.get("payload")
    if isinstance(pl, dict):
        inner = pl.get("result")
        if isinstance(inner, dict):
            return inner
    r = result.get("result")
    if isinstance(r, dict):
        return r
    return {}


def _queue_page_embed(current: str, items: list[str], page: int, page_size: int = QUEUE_PAGE_SIZE) -> discord.Embed:
    total = len(items)
    pages = max(1, (total + page_size - 1) // page_size)
    page = max(0, min(page, pages - 1))
    start = page * page_size
    end = min(start + page_size, total)
    page_items = items[start:end]
    embed = discord.Embed(
        title="Очередь воспроизведения",
        description="Нейра · музыкальный плеер",
        color=COL_BRAND,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="▶ Сейчас",
        value=_clip_field(current or "ничего не играет", EMBED_FIELD_SAFE),
        inline=False,
    )
    if page_items:
        lines = [f"`{start + idx + 1}.` {_clip_field(str(title), 180)}" for idx, title in enumerate(page_items)]
        q_body = _clip_field("\n".join(lines), EMBED_FIELD_SAFE)
        embed.add_field(name="В очереди", value=q_body, inline=False)
    else:
        embed.add_field(name="В очереди", value="Пусто.", inline=False)
    embed.add_field(name="Всего в очереди", value=str(total), inline=True)
    embed.set_footer(text=f"Страница {page + 1} из {pages} · листайте кнопками ниже")
    return embed


class QueuePagerView(discord.ui.View):
    def __init__(self, current: str, items: list[str], author_id: int, page_size: int = QUEUE_PAGE_SIZE):
        super().__init__(timeout=180)
        self.current = current
        self.items = items
        self.page_size = page_size
        self.page = 0
        self.author_id = author_id

    def _pages(self) -> int:
        total = len(self.items)
        return max(1, (total + self.page_size - 1) // self.page_size)

    async def _redraw(self, interaction: discord.Interaction) -> None:
        emb = _queue_page_embed(self.current, self.items, self.page, self.page_size)
        try:
            await interaction.response.edit_message(embed=emb, view=self)
        except discord.HTTPException:
            try:
                await interaction.response.send_message("Не удалось обновить сообщение.", ephemeral=True)
            except Exception:
                pass

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только автор запроса может листать очередь.", ephemeral=True)
            return
        self.page = (self.page - 1) % self._pages()
        await self._redraw(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:  # type: ignore[override]
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Только автор запроса может листать очередь.", ephemeral=True)
            return
        self.page = (self.page + 1) % self._pages()
        await self._redraw(interaction)


def _music_status_embed(
    title: str,
    description: str,
    *,
    color: int = COL_BRAND,
    footer: str = "Нейра · Discord",
) -> discord.Embed:
    emb = discord.Embed(
        title=title,
        description=_clip_field(description, 3800),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text=footer)
    return emb


class NeyraDiscordBot(discord.Client):
    def __init__(
        self,
        agent: "NeyraAgent",
        config: dict,
        reflection: Optional["ReflectionEngine"] = None,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.agent = agent
        self.config = config
        self.reflection = reflection
        disc_cfg = config.get("discord", {}) or {}

        self.active_channel_ids: set[int] = {int(c) for c in disc_cfg.get("channel_ids", [])}
        self.mention_only: bool = bool(disc_cfg.get("mention_only", False))
        self.stream_edit_interval: float = float(disc_cfg.get("stream_edit_interval", 0.8))
        self.stream_output_mode: str = str(disc_cfg.get("stream_output_mode", "stream")).strip().lower()
        self._cooldown: float = float(disc_cfg.get("cooldown_seconds", 3.0))
        self._last_response: dict[int, float] = {}
        self._music_waiters: dict[str, asyncio.Future] = {}
        self._music_timeout_s: float = float(disc_cfg.get("music_result_timeout_seconds", 25.0))

        self.agent.event_bus.subscribe(MUSIC_RESULT, self._on_music_result)

    @staticmethod
    def _candidate_music_intent(text: str) -> Optional[dict[str, str]]:
        raw = (text or "").strip()
        if not raw:
            return None
        lowered = raw.lower()
        if re.search(r"\b(читы|чит|hack|hax|aimbot)\b", lowered):
            return None
        direct = [
            (MUSIC_PAUSE, r"\b(пауза|pause|приостанови)\b"),
            (MUSIC_RESUME, r"\b(продолжи|resume|возобнови)\b"),
            (MUSIC_SKIP, r"\b(скип|skip|следующ|пропусти)\b"),
            (MUSIC_STOP, r"\b(стоп|stop|выключи музыку|останови музыку)\b"),
            (MUSIC_CLEAR, r"\b(очисти очередь|clear queue|clear)\b"),
            (MUSIC_QUEUE, r"\b(очередь|queue|что играет|что в очереди)\b"),
        ]
        for action, pattern in direct:
            if re.search(pattern, lowered):
                return {"intent": "music_control", "action": action, "query": ""}

        has_music_verb = bool(re.search(r"\b(включи|вруби|поставь|play|music|музыку|трек|track)\b", lowered))
        has_url = bool(re.search(r"https?://\S+", raw))
        if not has_music_verb and not has_url:
            return None
        q = re.sub(r"^(эй\s+нейра|нейра|please|пожалуйста)[,:\s-]*", "", raw, flags=re.IGNORECASE).strip()
        q = re.sub(r"^(включи|вруби|поставь|play|music|музыка)\s+", "", q, flags=re.IGNORECASE).strip()
        return {"intent": "music_control", "action": MUSIC_PLAY, "query": q}

    async def _confirm_music_intent(self, text: str, candidate: dict[str, str]) -> Optional[dict[str, str]]:
        # Non-play actions should stay deterministic and fast.
        if str(candidate.get("action") or "") != MUSIC_PLAY:
            return candidate
        # Stage-B semantic confirmation via LLM JSON output.
        if not getattr(self.agent, "llm_primary", None):
            return candidate
        prompt = (
            "Classify user text as music control intent.\n"
            "Return ONLY JSON: {\"is_music\":bool,\"action\":string,\"query\":string,\"confidence\":float}.\n"
            f"Allowed action: {MUSIC_PLAY},{MUSIC_PAUSE},{MUSIC_RESUME},{MUSIC_SKIP},{MUSIC_STOP},{MUSIC_CLEAR},{MUSIC_QUEUE}.\n"
            f"Candidate={json.dumps(candidate, ensure_ascii=False)}\n"
            f"Text={text}"
        )
        try:
            response = await self.agent.llm_primary.ainvoke(prompt)
            content = str(getattr(response, "content", "") or "")
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                return candidate
            data = json.loads(match.group(0))
            if not data.get("is_music"):
                return None
            confidence = float(data.get("confidence", 0.0))
            if confidence < 0.65:
                return None
            action = str(data.get("action") or candidate.get("action") or MUSIC_PLAY).strip()
            query = str(data.get("query") or candidate.get("query") or "").strip()
            return {"intent": "music_control", "action": action, "query": query}
        except Exception:
            return candidate

    def _on_music_result(self, event: CoreEvent) -> None:
        payload = event.payload or {}
        request_id = str(payload.get("request_id") or "")
        if not request_id:
            return
        fut = self._music_waiters.get(request_id)
        if fut and not fut.done():
            fut.set_result(payload)

    async def _publish_music_with_fallback(self, payload: dict[str, Any]) -> dict:
        request_id = str(payload.get("request_id") or "")
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        if request_id:
            self._music_waiters[request_id] = waiter
        self.agent.event_bus.publish(CoreEvent(str(payload.get("action") or MUSIC_PLAY), "interfaces.discord", payload))
        try:
            result_payload = await asyncio.wait_for(waiter, timeout=self._music_timeout_s)
            return {"ok": True, "mode": "event", "payload": result_payload}
        except asyncio.TimeoutError:
            # Stage A contract: discord text/music interact via Event Bus only.
            action = str(payload.get("action") or MUSIC_PLAY)
            counts = self.agent.event_bus.handler_counts()
            by_type = counts.get("by_type") if isinstance(counts, dict) else {}
            subscribed = int((by_type or {}).get(action, 0)) > 0
            if subscribed:
                # Consumer can still be processing (node failover / track search).
                return {"ok": True, "mode": "pending", "payload": {"action": action, "status": "pending"}}
            return {
                "ok": False,
                "mode": "event_timeout",
                "error": f"music consumer is not subscribed for action={action}",
            }
        finally:
            if request_id:
                self._music_waiters.pop(request_id, None)

    async def on_ready(self):
        # Shared runtime handle for in-process music + other Discord-adjacent plugins.
        self.agent.discord_client = self
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="текст и музыка · Нейра")
        )
        logger.info("Discord online: %s (ID: %s)", self.user, self.user.id if self.user else "?")
        if self.active_channel_ids:
            logger.info("Активные каналы: %s", self.active_channel_ids)
        else:
            logger.info("Активных каналов нет — отвечаю только на @mention")

    async def setup_hook(self) -> None:
        @self.tree.command(name="reset", description="Сбросить краткую память диалога")
        async def slash_reset(interaction: discord.Interaction):
            self.agent.reset_context(str(interaction.channel_id))
            await interaction.response.send_message("Память сброшена.", ephemeral=True)

        @self.tree.command(name="time", description="Текущие дата и время")
        async def slash_time(interaction: discord.Interaction):
            out = self.agent.tools["get_current_time"].invoke({})
            await interaction.response.send_message(str(out), ephemeral=True)

        @self.tree.command(name="sys", description="Система: CPU, RAM, диск, аптайм")
        @app_commands.describe(metric="Что показать")
        @app_commands.choices(
            metric=[
                Choice(name="uptime", value="uptime"),
                Choice(name="disk", value="disk"),
                Choice(name="memory", value="memory"),
                Choice(name="cpu", value="cpu"),
                Choice(name="python", value="python"),
            ]
        )
        async def slash_sys(interaction: discord.Interaction, metric: str):
            raw = self.agent.tools["check_system"].invoke({"command": metric})
            await interaction.response.send_message(f"```\n{str(raw)[:1900]}\n```", ephemeral=True)

        @self.tree.command(name="web", description="Поиск в интернете")
        @app_commands.describe(query="Запрос")
        async def slash_web(interaction: discord.Interaction, query: str):
            q = (query or "").strip()
            if not q:
                await interaction.response.send_message("Укажи запрос.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            raw = self.agent.tools["web_search"].invoke({"query": q[:500]})
            await interaction.followup.send(f"```\n{str(raw)[:1900]}\n```", ephemeral=True)

        @self.tree.command(name="person", description="Досье из PeopleDB")
        @app_commands.describe(name_or_id="Имя или id")
        async def slash_person(interaction: discord.Interaction, name_or_id: str):
            key = (name_or_id or "").strip()
            if not key:
                await interaction.response.send_message("Укажи имя или id.", ephemeral=True)
                return
            raw = self.agent.tools["get_person_info"].invoke({"name_or_id": key[:120]})
            await interaction.response.send_message(f"```\n{str(raw)[:1900]}\n```", ephemeral=True)

        @self.tree.command(name="stats", description="Статистика агента и системы")
        async def slash_stats(interaction: discord.Interaction):
            import psutil

            s = self.agent.get_stats()
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            lines = [
                "**Статистика**",
                f"Режим: {s['mode'].upper()}",
                f"Модель: {s['model']}",
                f"Память диалога: {s['short_memory_size']} сообщений",
                f"RAG: {s['long_memory_records']} записей",
                f"Людей в БД: {s.get('people_db_records', 0)}",
                "",
                f"CPU: {cpu}%",
                f"ОЗУ: {mem.percent}% ({mem.used // 1024**2} МБ / {mem.total // 1024**2} МБ)",
            ]
            await interaction.response.send_message("\n".join(lines), ephemeral=True)

        @self.tree.command(name="journal", description="Дневник рефлексии за 7 дней")
        async def slash_journal(interaction: discord.Interaction):
            if not self.reflection:
                await interaction.response.send_message("Рефлексия отключена.", ephemeral=True)
                return
            journal = self.reflection.get_recent_journal(7) or "*Пусто*"
            await interaction.response.send_message(
                f"**Дневник (7 дней)**\n```\n{str(journal)[:1800]}\n```", ephemeral=True
            )

        @self.tree.command(name="diary", description="Личный дневник Нейры")
        @app_commands.describe(limit="Сколько записей показать (1-30)")
        async def slash_diary(interaction: discord.Interaction, limit: app_commands.Range[int, 1, 30] = 12):
            body = self.agent.get_recent_diary(int(limit))
            await interaction.response.send_message(
                f"**Личный дневник Нейры**\n```\n{str(body)[:1800]}\n```",
                ephemeral=True,
            )

        @self.tree.command(name="diary_add", description="Добавить запись в личный дневник Нейры")
        @app_commands.describe(text="Текст заметки")
        async def slash_diary_add(interaction: discord.Interaction, text: str):
            note = (text or "").strip()
            if not note:
                await interaction.response.send_message("Пустая запись.", ephemeral=True)
                return
            ok = self.agent.add_diary_entry(
                note,
                source="manual_discord",
                meta={"author": interaction.user.name, "channel_id": int(interaction.channel_id)},
            )
            await interaction.response.send_message(
                "Записала в личный дневник." if ok else "Не смогла записать в дневник.",
                ephemeral=True,
            )

        @self.tree.command(name="reflect", description="Запустить рефлексию вручную")
        async def slash_reflect(interaction: discord.Interaction):
            if not self.reflection:
                await interaction.response.send_message("Рефлексия отключена.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            summary = await self.reflection.reflect(force=True)
            await interaction.followup.send(
                f"**Рефлексия**\n```\n{str(summary)[:1900]}\n```" if summary else "Нечего рефлексировать."
            )

        @self.tree.command(name="search", description="Поиск по долгосрочной памяти (RAG)")
        @app_commands.describe(query="Текст поиска")
        async def slash_search(interaction: discord.Interaction, query: str):
            q = (query or "").strip()
            if not q:
                await interaction.response.send_message("Введи запрос.", ephemeral=True)
                return
            results = self.agent.long_memory.search(q)
            if not results:
                await interaction.response.send_message("Ничего не нашла.", ephemeral=True)
                return
            text_out = "\n\n".join(r[:300] for r in results)[:1900]
            await interaction.response.send_message(f"**Поиск**\n```\n{text_out}\n```", ephemeral=True)

        @self.tree.error
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            logger.exception("Slash: %s", error)
            try:
                msg = f"Ошибка команды: {error}"
                if interaction.response.is_done():
                    await interaction.followup.send(msg[:2000], ephemeral=True)
                else:
                    await interaction.response.send_message(msg[:2000], ephemeral=True)
            except Exception:
                pass

        disc = self.config.get("discord", {}) or {}
        raw_gid = disc.get("slash_sync_guild_id")
        if raw_gid is not None and str(raw_gid).strip().lower() not in ("", "null", "none"):
            guild = discord.Object(id=int(raw_gid))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash-команды синхронизированы для гильдии %s", raw_gid)
        else:
            await self.tree.sync()
            logger.info("Slash-команды синхронизированы глобально")

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        mentioned = self.user in message.mentions
        in_active = message.channel.id in self.active_channel_ids
        if self.mention_only:
            if not mentioned:
                return
        else:
            if not mentioned and not in_active:
                return

        user_id = message.author.id
        now = time.monotonic()
        if now - self._last_response.get(user_id, 0.0) < self._cooldown:
            return
        self._last_response[user_id] = now

        vision_imgs = await self._collect_image_attachments(message)
        content = message.content
        for mention in message.mentions:
            content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        content = content.strip() or "*молчишь*"
        if vision_imgs and content == "*молчишь*":
            content = "Что на изображении? Коротко по-русски."

        candidate = self._candidate_music_intent(content)
        if candidate:
            resolved = await self._confirm_music_intent(content, candidate)
        else:
            resolved = None

        if resolved:
            request_id = f"{message.id}:{int(time.time() * 1000)}"
            guild_id = str(message.guild.id) if message.guild else ""
            action = str(resolved.get("action") or MUSIC_PLAY)
            query = str(resolved.get("query") or "").strip()
            randomize = action == MUSIC_PLAY and bool(
                re.search(r"\b(любой|рандом|случайн)\b", content, flags=re.IGNORECASE)
            )
            voice_channel_id = ""
            try:
                if message.author.voice and message.author.voice.channel:
                    voice_channel_id = str(message.author.voice.channel.id)
            except Exception:
                voice_channel_id = ""
            payload = {
                "action": action,
                "query": query,
                "requester_id": str(message.author.id),
                "text_channel_id": str(message.channel.id),
                "voice_channel_id": voice_channel_id,
                "guild_id": guild_id,
                "request_id": request_id,
                "idempotency_key": f"{message.id}:{guild_id}:{message.author.id}:{action}",
                "source_message_id": str(message.id),
                "ts": time.time(),
                "randomize": randomize,
                "random_top_k": 5,
                "use_brain": False,
            }
            result = await self._publish_music_with_fallback(payload)
            if result.get("ok"):
                mode = str(result.get("mode") or "")
                res_inner = _normalize_music_handler_result(result)
                status = str(res_inner.get("status") or "")
                if status == "failed":
                    err = str(res_inner.get("error") or "unknown error")
                    await message.reply(
                        embed=_music_status_embed(
                            "Не получилось",
                            f"Команда не выполнена.\n```{_clip_field(err, 900)}```",
                            color=COL_ERR,
                        ),
                        mention_author=False,
                    )
                    return
                if action == MUSIC_QUEUE:
                    current = str(res_inner.get("current") or "").strip()
                    queue_items = res_inner.get("queue") if isinstance(res_inner.get("queue"), list) else []
                    queue_items = [str(x) for x in queue_items]
                    emb = _queue_page_embed(current, queue_items, 0, QUEUE_PAGE_SIZE)
                    view = QueuePagerView(current, queue_items, author_id=message.author.id, page_size=QUEUE_PAGE_SIZE)
                    await message.reply(embed=emb, view=view, mention_author=False)
                    return
                if mode == "pending":
                    await message.reply(
                        embed=_music_status_embed(
                            "Долго думаю",
                            "Поиск трека или подключение к Lavalink заняли больше обычного. "
                            "Пока обработка идёт в фоне — если ответа не будет, повтори команду через несколько секунд.",
                            color=COL_WARN,
                        ),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_PLAY:
                    track = str(res_inner.get("track") or "").strip()
                    author = str(res_inner.get("author") or "").strip()
                    candidates = res_inner.get("candidates") if isinstance(res_inner.get("candidates"), list) else []
                    if track and author:
                        base = f"**{author}** — **{track}**"
                    else:
                        base = f"**{_clip_field(track or 'неизвестный трек', 500)}**"
                    if status == "queued":
                        title = "В очереди"
                        desc = base
                        col = COL_BRAND
                    elif status in ("started",):
                        title = "Играет"
                        desc = base
                        col = COL_OK
                    else:
                        title = "Музыка"
                        desc = base or "Готово."
                        col = COL_BRAND
                    if candidates:
                        found = "\n".join([f"・ {_clip_field(str(x), 120)}" for x in candidates[:5]])
                        desc += f"\n\n**Варианты поиска:**\n{found}"
                    await message.reply(
                        embed=_music_status_embed(title, _clip_field(desc, 3800), color=col),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_SKIP:
                    next_title = str(res_inner.get("next") or "").strip()
                    desc = "Текущий трек пропущен."
                    if next_title:
                        desc += f"\n\nДальше: **{_clip_field(next_title, 400)}**"
                    await message.reply(
                        embed=_music_status_embed("Пропуск", desc, color=COL_OK),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_STOP:
                    await message.reply(
                        embed=_music_status_embed("Стоп", "Воспроизведение остановлено.", color=COL_BRAND),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_PAUSE:
                    await message.reply(
                        embed=_music_status_embed("Пауза", "Плеер на паузе.", color=COL_WARN),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_RESUME:
                    await message.reply(
                        embed=_music_status_embed("Продолжить", "Сняла с паузы.", color=COL_OK),
                        mention_author=False,
                    )
                    return
                elif action == MUSIC_CLEAR:
                    await message.reply(
                        embed=_music_status_embed("Очередь", "Очередь очищена.", color=COL_BRAND),
                        mention_author=False,
                    )
                    return
                else:
                    await message.reply(
                        embed=_music_status_embed("Музыка", "Команда выполнена.", color=COL_OK),
                        mention_author=False,
                    )
                    return
            else:
                fail = str(result.get("error") or "").strip()
                if not fail:
                    inner = _normalize_music_handler_result(result)
                    fail = str(inner.get("error") or inner.get("status") or "unknown error")
                await message.reply(
                    embed=_music_status_embed(
                        "Музыка недоступна",
                        f"```{_clip_field(fail, 900)}```",
                        color=COL_ERR,
                    ),
                    mention_author=False,
                )
            return

        asyncio.create_task(
            self._run_chat_stream(
                text_channel=message.channel,
                starter_message=message,
                content=content,
                username=message.author.name,
                discord_user_id=str(message.author.id),
                channel_id_str=str(message.channel.id),
                vision_images=vision_imgs if vision_imgs else None,
            )
        )

    async def _collect_image_attachments(self, message: discord.Message) -> list[tuple[str, str]]:
        from core.vision_util import prepare_image_for_vision, resolve_discord_image_mime

        vis = self.config.get("vision") or {}
        if not vis.get("enabled"):
            return []
        max_n = int(vis.get("max_images_per_message", 4))
        max_b = int(vis.get("max_image_bytes", 5_242_880))
        max_w = int(vis.get("max_image_width", 1280))
        max_h = int(vis.get("max_image_height", 720))
        loop = asyncio.get_running_loop()
        out: list[tuple[str, str]] = []
        for att in message.attachments:
            if len(out) >= max_n:
                break
            ct = resolve_discord_image_mime(att.content_type, att.filename or "")
            if not ct:
                continue
            if att.size and att.size > max_b:
                continue
            try:
                data = await att.read()
            except Exception:
                continue
            if len(data) > max_b:
                continue
            data, ct = await loop.run_in_executor(
                None,
                functools.partial(prepare_image_for_vision, data, ct, max_w, max_h),
            )
            b64 = base64.standard_b64encode(data).decode("ascii")
            out.append((ct, b64))
        return out

    async def _run_chat_stream(
        self,
        *,
        text_channel: discord.TextChannel,
        starter_message: Optional[discord.Message],
        content: str,
        username: str,
        discord_user_id: str,
        channel_id_str: str,
        vision_images: Optional[list[tuple[str, str]]],
    ) -> None:
        async with text_channel.typing():
            response_msg = (
                await starter_message.reply(THINKING_DOT, mention_author=False)
                if starter_message
                else await text_channel.send(THINKING_DOT)
            )
            full_raw = ""
            last_edit = asyncio.get_event_loop().time()
            done_data: dict = {}
            output_mode = self._resolve_stream_output_mode()

            try:
                async for chunk in self.agent.chat_stream(
                    content,
                    username=username,
                    discord_user_id=discord_user_id,
                    vision_images=vision_images,
                    channel_id=channel_id_str,
                ):
                    if chunk["type"] == "token":
                        full_raw += chunk["text"]
                        if output_mode == "final_only":
                            continue
                        now = asyncio.get_event_loop().time()
                        if now - last_edit >= self.stream_edit_interval:
                            preview = self._make_preview(full_raw)
                            try:
                                await response_msg.edit(content=preview + THINKING_DOT)
                                last_edit = now
                            except discord.HTTPException:
                                pass
                    elif chunk["type"] == "done":
                        done_data = chunk
                    elif chunk["type"] == "error":
                        err = chunk.get("text", "")
                        await response_msg.edit(content=f"⚠️ {err or 'ошибка генерации'}")
                        return

                final_text = done_data.get("text", full_raw).strip() or "*(пустой ответ)*"
                parts = _split_message(final_text)
                await response_msg.edit(content=parts[0])
                sent_ids: list[int] = [response_msg.id]
                for part in parts[1:]:
                    sent = await text_channel.send(part)
                    sent_ids.append(sent.id)
                internal_uid = (
                    self.agent.identity.resolve_from_discord(discord_user_id)
                    or self.agent.identity.resolve_console(username)
                )
                self.agent.event_bus.publish(
                    CoreEvent(
                        NOTIFY_DISCORD_MESSAGE_SENT,
                        "interfaces.discord",
                        {
                            "user_id": internal_uid,
                            "channel_id": channel_id_str,
                            "message_ids": sent_ids,
                            "parts": len(parts),
                        },
                    )
                )
            except Exception as e:
                logger.exception("Ошибка в _run_chat_stream: %s", e)
                try:
                    await response_msg.edit(content=f"⚠️ Что-то сломалось: {e}")
                except Exception:
                    pass

    def _make_preview(self, raw: str) -> str:
        text = re.sub(
            r"<(?:redacted_thinking|think|thought)>.*?</(?:redacted_thinking|think|thought)>",
            "",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        )
        text = re.sub(r"<(?:redacted_thinking|think|thought)>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"</?(?:redacted_thinking|think|thought)>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\[[^\]]*\]", "", text).strip()
        if len(text) > MAX_MSG_LEN - 10:
            text = text[: MAX_MSG_LEN - 10]
        return text

    def _resolve_stream_output_mode(self) -> str:
        return "final_only" if self.stream_output_mode == "final_only" else "stream"


def _split_message(text: str) -> list[str]:
    if len(text) <= MAX_MSG_LEN:
        return [text]
    parts = []
    while len(text) > MAX_MSG_LEN:
        split_at = text.rfind("\n", 0, MAX_MSG_LEN)
        if split_at == -1:
            split_at = MAX_MSG_LEN
        parts.append(text[:split_at])
        text = text[split_at:].lstrip()
    if text:
        parts.append(text)
    return parts


def run_discord_bot(agent: "NeyraAgent", config: dict) -> None:
    disc_cfg = config.get("discord", {})
    token = (os.environ.get("DISCORD_TOKEN") or "").strip() or (disc_cfg.get("token") or "").strip()
    if not token:
        raise ValueError("Задайте DISCORD_TOKEN в .env (или legacy discord.token в конфиге)")

    from core.reflection import ReflectionEngine

    bot = NeyraDiscordBot(agent, config, reflection=ReflectionEngine(config, agent))
    logger.info("Запускаю Discord-бот (текст + музыка)...")
    bot.run(token, log_handler=None)
