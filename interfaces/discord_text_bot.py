"""
Текстовый Discord-бот Нейры (без voice/STT/TTS).

Задача интерфейса:
- принимать текст и картинки из Discord;
- вызывать core.agent;
- отправлять ответ в текстовый канал.
"""

from __future__ import annotations

import asyncio
import base64
import functools
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.app_commands import Choice

if TYPE_CHECKING:
    from core.agent import NeyraAgent
    from core.reflection import ReflectionEngine

logger = logging.getLogger("neyra.discord")

MAX_MSG_LEN = 1900
THINKING_DOT = "▌"


class NeyraDiscordTextBot(discord.Client):
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

    async def on_ready(self):
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="текстовые сообщения")
        )
        logger.info("Discord Text Online: %s (ID: %s)", self.user, self.user.id if self.user else "?")
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

        @self.tree.command(name="friend", description="Досье из FriendsDB")
        @app_commands.describe(name_or_id="Имя или id")
        async def slash_friend(interaction: discord.Interaction, name_or_id: str):
            key = (name_or_id or "").strip()
            if not key:
                await interaction.response.send_message("Укажи имя или id.", ephemeral=True)
                return
            raw = self.agent.tools["get_friend_info"].invoke({"name_or_id": key[:120]})
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
                f"Людей в БД: {s['friends_db_records']}",
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
                for part in parts[1:]:
                    await text_channel.send(part)
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


def run_discord_text_bot(agent: "NeyraAgent", config: dict) -> None:
    disc_cfg = config.get("discord", {})
    token = (disc_cfg.get("token") or "").strip() or (os.environ.get("DISCORD_TOKEN") or "").strip()
    if not token or token == "ВАШ_ТОКЕН_СЮДА":
        raise ValueError("DISCORD_TOKEN не задан в .env")

    from core.reflection import ReflectionEngine

    bot = NeyraDiscordTextBot(agent, config, reflection=ReflectionEngine(config, agent))
    logger.info("Запускаю Discord text-бот...")
    bot.run(token, log_handler=None)
