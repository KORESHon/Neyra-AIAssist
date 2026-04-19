"""
core/reflection.py — Ночная рефлексия Нейры
─────────────────────────────────────────────
APScheduler запускает задачу в 04:00 каждую ночь.
LLM суммирует диалоги за день → journal.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import re

logger = logging.getLogger("neyra.reflection")


class ReflectionEngine:
    """Движок ночной рефлексии."""

    def __init__(self, config: dict, agent=None):
        self.config = config
        self.agent = agent  # Ссылка на NeyraAgent (для вызова LLM)

        mem_cfg = config.get("memory", {})
        self.journal_path = Path(mem_cfg.get("journal_path", "./memory/journal.json"))
        self.diary_path = Path(mem_cfg.get("diary_path", "./memory/neyra_diary.jsonl"))
        self.reflect_json_path = Path(mem_cfg.get("reflection_json_path", "./memory/reflection_last.json"))
        self.chat_log_path = Path(config["logging"]["chat_log"])
        self.reflection_time = mem_cfg.get("reflection_time", "04:00")
        self.small_reflection_enabled = bool(mem_cfg.get("small_reflection_enabled", True))
        self.small_reflection_hours = max(1, int(mem_cfg.get("small_reflection_hours", 4)))
        self.small_reflection_min_lines = int(mem_cfg.get("small_reflection_min_lines", 8))
        self.small_reflection_max_chars = int(mem_cfg.get("small_reflection_max_chars", 1400))
        self.diary_hourly_enabled = bool(mem_cfg.get("diary_hourly_enabled", True))
        self.diary_hourly_min_lines = int(mem_cfg.get("diary_hourly_min_lines", 6))
        self._last_hourly_key: str = ""
        self._last_small_key: str = ""

        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

        # Загружаем существующий журнал
        self._journal: list[dict] = self._load_journal()

    def _load_journal(self) -> list:
        if self.journal_path.exists():
            try:
                return json.loads(self.journal_path.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_journal(self):
        self.journal_path.write_text(
            json.dumps(self._journal, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        agent = getattr(self, "agent", None)
        bus = getattr(agent, "event_bus", None) if agent is not None else None
        if bus is not None:
            from core.event_bus import MEMORY_JOURNAL_UPDATED, CoreEvent

            bus.publish(
                CoreEvent(
                    MEMORY_JOURNAL_UPDATED,
                    "core.reflection",
                    {"path": str(self.journal_path), "entries": len(self._journal)},
                )
            )

    def _get_logs_for_date(self, date: datetime) -> str:
        """Читает строки из chat.log за указанную дату."""
        if not self.chat_log_path.exists():
            return ""

        date_str = date.strftime("%Y-%m-%d")
        lines = []
        try:
            for line in self.chat_log_path.read_text(encoding="utf-8").splitlines():
                if date_str in line:
                    lines.append(line)
        except Exception as e:
            logger.error(f"Ошибка чтения chat.log: {e}")

        return "\n".join(lines)

    def _get_logs_for_last_hour(self) -> str:
        """Читает свежие строки chat.log за последний час."""
        if not self.chat_log_path.exists():
            return ""
        cutoff = datetime.now() - timedelta(hours=1)
        lines: list[str] = []
        try:
            for line in self.chat_log_path.read_text(encoding="utf-8").splitlines():
                # Формат: [YYYY-MM-DD HH:MM:SS] ...
                if not line.startswith("[") or "]" not in line:
                    continue
                ts_str = line[1 : line.find("]")]
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if ts >= cutoff:
                    lines.append(line)
        except Exception as e:
            logger.error(f"Ошибка чтения hourly chat.log: {e}")
        return "\n".join(lines)

    def _get_logs_for_last_hours(self, hours: int) -> str:
        """Читает строки chat.log за последние N часов."""
        if not self.chat_log_path.exists():
            return ""
        cutoff = datetime.now() - timedelta(hours=max(1, int(hours)))
        lines: list[str] = []
        try:
            for line in self.chat_log_path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("[") or "]" not in line:
                    continue
                ts_str = line[1 : line.find("]")]
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if ts >= cutoff:
                    lines.append(line)
        except Exception as e:
            logger.error("Ошибка чтения chat.log за %s часов: %s", hours, e)
        return "\n".join(lines)

    async def reflect(self, date: datetime = None, force: bool = False) -> str:
        """Ночная рефлексия: дневник за 24ч -> JSON (people_updates/global_lore/behavior_rules)."""
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")
        logger.info("Запускаю self-reflection за %s (force=%s)", date_str, force)

        # Для ночного крона — не запускать повторно в тот же день; /reflect может передать force=True.
        if not force and any(e.get("date") == date_str for e in self._journal):
            logger.info("Рефлексия за %s уже есть, пропускаю", date_str)
            return ""

        diary_lines = self._get_diary_last_24h()
        if not diary_lines:
            logger.info("Дневник за 24ч пуст — рефлексию пропускаю")
            return ""

        result = await self._analyze_diary_json(diary_lines, date_str)
        if not result:
            return ""
        self._apply_reflection_result(result)

        try:
            self.reflect_json_path.parent.mkdir(parents=True, exist_ok=True)
            self.reflect_json_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Не удалось записать reflection_last.json: %s", e)

        summary = self._compact_summary(result)
        if summary:
            self._journal.append({
                "date": date_str,
                "summary": summary,
                "reflection_json": result,
                "generated_at": datetime.now().isoformat(),
            })
            self._save_journal()
            logger.info("Рефлексия за %s сохранена", date_str)
            await self._auto_sync_external_backup()

        return summary

    async def _auto_sync_external_backup(self) -> None:
        """Автосинхронизация бэкапа после большой рефлексии (если включено в конфиге)."""
        cfg = self.config.get("external_storage") or {}
        if not bool(cfg.get("enabled", False)):
            return
        sync_after = bool(cfg.get("sync_after_big_reflection", True))
        if not sync_after:
            return
        try:
            from core.backup_manager import BackupManager

            mgr = BackupManager(self.config)
            res = await asyncio.to_thread(mgr.run_backup, "post_big_reflection")
            logger.info("External storage auto-sync done: %s", res.get("external_ref") or res.get("archive"))
        except Exception as e:
            logger.warning("External storage auto-sync failed: %s", e)

    @staticmethod
    def _normalize_fact_text(text: str) -> str:
        t = (text or "").strip().lower()
        t = re.sub(r"\s+", " ", t)
        return t

    @staticmethod
    def _is_high_signal_fact(text: str) -> bool:
        """Фильтр «важность/мусор» для записи фактов в долговременную память."""
        t = (text or "").strip()
        if len(t) < 12:
            return False
        low = t.lower()
        # Явный мусор/мета.
        trash_markers = (
            "не знаю",
            "без изменений",
            "ничего нового",
            "просто поболтали",
            "шутка",
            "мем без факта",
        )
        if any(m in low for m in trash_markers):
            return False
        # Наличие признаков значимого факта.
        important_markers = (
            "работ",
            "учеб",
            "переех",
            "отношен",
            "боле",
            "конфликт",
            "помир",
            "проект",
            "план",
            "договор",
            "деньги",
            "покуп",
            "продал",
            "сменил",
            "цель",
            "проблем",
        )
        if any(m in low for m in important_markers):
            return True
        # Если маркеров нет, но фраза достаточно содержательная — оставляем.
        return len(t) >= 30

    def _apply_reflection_result(self, result: dict) -> None:
        """Большая рефлексия: запись устойчивых фактов в PeopleDB + дневник."""
        if not self.agent:
            return
        people_db = getattr(self.agent, "people_db", None)
        diary = getattr(self.agent, "diary", None)
        if people_db is None:
            return

        updates = list(result.get("people_updates") or [])
        existing_norm: dict[str, set[str]] = {}
        for pid, person in getattr(people_db, "_cache", {}).items():
            norms: set[str] = set()
            for row in list(person.get("dynamic_facts") or []):
                norms.add(self._normalize_fact_text(str(row.get("fact") or "")))
            existing_norm[pid] = norms

        added: list[str] = []
        for item in updates:
            if not isinstance(item, dict):
                continue
            hint = str(item.get("person_hint") or "").strip()
            fact = str(item.get("fact") or "").strip()
            if not hint or not fact or not self._is_high_signal_fact(fact):
                continue
            person = people_db.find(hint)
            if not person:
                continue
            pid = str(person.get("id") or "").strip()
            if not pid:
                continue
            norm = self._normalize_fact_text(fact)
            if not norm:
                continue
            if norm in existing_norm.setdefault(pid, set()):
                continue
            ok = people_db.update_fact(pid, fact)
            if ok:
                existing_norm[pid].add(norm)
                added.append(f"{pid}: {fact}")

        if diary is not None:
            lore = [str(x).strip() for x in list(result.get("global_lore") or []) if str(x).strip()]
            rules = [str(x).strip() for x in list(result.get("behavior_rules") or []) if str(x).strip()]
            if added:
                diary.add_entry(
                    text="Большая рефлексия: закрепила факты в PeopleDB:\n- " + "\n- ".join(added[:8]),
                    source="nightly_reflection_apply",
                    meta={"facts_added": len(added)},
                )
            if lore:
                diary.add_entry(
                    text="Большая рефлексия: глобальные наблюдения:\n- " + "\n- ".join(lore[:6]),
                    source="nightly_reflection_apply",
                    meta={"global_lore_count": len(lore)},
                )
            if rules:
                diary.add_entry(
                    text="Большая рефлексия: правила поведения:\n- " + "\n- ".join(rules[:4]),
                    source="nightly_reflection_apply",
                    meta={"behavior_rules_count": len(rules)},
                )

    async def small_reflection(self) -> str:
        """Малая рефлексия (каждые N часов): сжатие активного контекста в дневник."""
        if not self.agent or not hasattr(self.agent, "diary"):
            return ""
        now = datetime.now()
        block_start = (now.hour // self.small_reflection_hours) * self.small_reflection_hours
        key = now.strftime("%Y-%m-%d") + f" {block_start:02d}"
        if self._last_small_key == key:
            return ""
        logs = self._get_logs_for_last_hours(self.small_reflection_hours)
        if len([x for x in logs.splitlines() if x.strip()]) < self.small_reflection_min_lines:
            return ""
        prompt = (
            f"Сожми контекст последних {self.small_reflection_hours} часов в 2-4 коротких предложения. "
            "Только практичные наблюдения для памяти: кто, что изменилось, какие темы/риски. "
            "Без markdown и списков.\n\n"
            f"Логи:\n{logs[:5000]}"
        )
        try:
            from langchain_core.messages import HumanMessage

            llm_reflect = getattr(self.agent, "llm_reflection", self.agent.llm)
            response = await llm_reflect.ainvoke([HumanMessage(content=prompt)])
            note = str(response.content).strip()
            if not note:
                return ""
            if len(note) > self.small_reflection_max_chars:
                note = note[: self.small_reflection_max_chars - 1] + "…"
            ok = self.agent.diary.add_entry(
                text=note,
                source="small_reflection",
                meta={"hours": self.small_reflection_hours, "key": key},
            )
            if ok:
                self._last_small_key = key
                logger.info("Добавлена малая рефлексия за блок %s", key)
                return note
            return ""
        except Exception as e:
            logger.error("Ошибка small_reflection: %s", e)
            return ""

    def _get_diary_last_24h(self) -> str:
        """Читает записи из neyra_diary.jsonl за последние 24 часа."""
        if not self.diary_path.exists():
            return ""
        cutoff = datetime.now() - timedelta(hours=24)
        rows: list[str] = []
        try:
            for line in self.diary_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                ts_raw = str(item.get("timestamp") or "").strip()
                if not ts_raw:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_raw)
                except Exception:
                    continue
                if ts < cutoff:
                    continue
                source = str(item.get("source") or "unknown")
                text = str(item.get("text") or "").strip()
                if text:
                    rows.append(f"[{ts.strftime('%Y-%m-%d %H:%M')} | {source}] {text}")
        except Exception as e:
            logger.error("Ошибка чтения дневника за 24ч: %s", e)
        return "\n".join(rows)

    @staticmethod
    def _extract_json_blob(raw: str) -> str:
        t = (raw or "").strip()
        if not t:
            return ""
        if t.startswith("```"):
            lines = t.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines).strip()
        start = t.find("{")
        end = t.rfind("}")
        if start >= 0 and end > start:
            return t[start : end + 1]
        return t

    async def _analyze_diary_json(self, diary_24h: str, date_str: str) -> dict:
        """LLM-анализ дневника за 24ч в строгий JSON."""
        if self.agent is None:
            return {
                "people_updates": [],
                "global_lore": [],
                "behavior_rules": [],
            }

        prompt = (
            "Ты аналитический модуль памяти Нейры. Верни ответ СТРОГО в JSON без пояснений и markdown.\n"
            "Формат:\n"
            "{\n"
            '  "people_updates": [{"person_hint":"...", "fact":"..."}],\n'
            '  "global_lore": ["..."],\n'
            '  "behavior_rules": ["..."]\n'
            "}\n"
            "Ограничения:\n"
            "- Только факты/мемы/правила из лога ниже.\n"
            "- behavior_rules: максимум 2 пункта.\n"
            "- Если данных нет: пустые массивы.\n\n"
            f"Дата: {date_str}\n"
            f"Лог дневника за 24 часа:\n{diary_24h[:12000]}"
        )

        try:
            from langchain_core.messages import HumanMessage
            llm_reflect = getattr(self.agent, "llm_reflection", self.agent.llm)
            response = await llm_reflect.ainvoke([HumanMessage(content=prompt)])
            raw = str(response.content).strip()
            blob = self._extract_json_blob(raw)
            data = json.loads(blob)
            return {
                "people_updates": list(data.get("people_updates") or []),
                "global_lore": list(data.get("global_lore") or []),
                "behavior_rules": list(data.get("behavior_rules") or [])[:2],
            }
        except Exception as e:
            logger.error("Ошибка LLM-анализа рефлексии: %s", e)
            return {"people_updates": [], "global_lore": [], "behavior_rules": []}

    @staticmethod
    def _compact_summary(data: dict) -> str:
        fu = len(list(data.get("people_updates") or []))
        gl = len(list(data.get("global_lore") or []))
        br = len(list(data.get("behavior_rules") or []))
        return f"Self-reflection: people_updates={fu}, global_lore={gl}, behavior_rules={br}"

    async def hourly_diary_note(self) -> str:
        """Пишет почасовую заметку в личный дневник Нейры."""
        if not self.agent or not hasattr(self.agent, "diary"):
            return ""

        now = datetime.now()
        hour_key = now.strftime("%Y-%m-%d %H")
        if self._last_hourly_key == hour_key:
            return ""  # уже писали в этот час

        logs = self._get_logs_for_last_hour()
        if len([x for x in logs.splitlines() if x.strip()]) < self.diary_hourly_min_lines:
            return ""

        prompt = (
            "Сделай ОДНУ короткую заметку (1-3 предложения) для личного дневника Нейры "
            "по диалогам за последний час. От первого лица, разговорно: что заметила в людях, "
            "настроении, темах. Без markdown и списков.\n\n"
            f"Логи за час:\n{logs[:3500]}"
        )
        try:
            from langchain_core.messages import HumanMessage

            llm_reflect = getattr(self.agent, "llm_reflection", self.agent.llm)
            response = await llm_reflect.ainvoke([HumanMessage(content=prompt)])
            note = str(response.content).strip()
            if not note:
                return ""
            ok = self.agent.diary.add_entry(
                text=note,
                source="hourly_auto",
                meta={"hour": hour_key},
            )
            if ok:
                self._last_hourly_key = hour_key
                logger.info("Добавлена почасовая запись дневника за %s", hour_key)
                return note
            return ""
        except Exception as e:
            logger.error("Ошибка hourly_diary_note: %s", e)
            return ""

    def start_scheduler(self):
        """Запускает APScheduler для ночной рефлексии."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            hour, minute = map(int, self.reflection_time.split(":"))
            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                self.reflect,
                trigger="cron",
                hour=hour,
                minute=minute,
                id="nightly_reflection",
                kwargs={"force": False},
            )
            if self.small_reflection_enabled:
                scheduler.add_job(
                    self.small_reflection,
                    trigger="cron",
                    hour=f"*/{self.small_reflection_hours}",
                    minute=15,
                    id="small_reflection",
                )
            if self.diary_hourly_enabled:
                scheduler.add_job(
                    self.hourly_diary_note,
                    trigger="cron",
                    minute=0,
                    id="hourly_diary_note",
                )
            scheduler.start()
            logger.info(f"Рефлексия запланирована на {self.reflection_time} каждую ночь")
            if self.small_reflection_enabled:
                logger.info(
                    "Малая рефлексия: каждые %sч (minute=15)",
                    self.small_reflection_hours,
                )
            if self.diary_hourly_enabled:
                logger.info("Личный дневник: автозапись каждый час (minute=00)")
            return scheduler
        except ImportError:
            logger.warning("APScheduler не установлен. Рефлексия отключена.")
            return None

    def get_recent_journal(self, days: int = 7) -> str:
        """Возвращает записи журнала за последние N дней."""
        recent = self._journal[-days:] if self._journal else []
        if not recent:
            return "Журнал пустой."
        lines = []
        for entry in recent:
            lines.append(f"[{entry['date']}] {entry['summary']}")
        return "\n".join(lines)
