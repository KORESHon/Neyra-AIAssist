"""
core/reflection.py — Ночная рефлексия Нейры
─────────────────────────────────────────────
APScheduler запускает задачу в 04:00 каждую ночь.
LLM суммирует диалоги за день → journal.json.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

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
        self.diary_hourly_enabled = bool(mem_cfg.get("diary_hourly_enabled", True))
        self.diary_hourly_min_lines = int(mem_cfg.get("diary_hourly_min_lines", 6))
        self._last_hourly_key: str = ""

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

    async def reflect(self, date: datetime = None, force: bool = False) -> str:
        """Ночная рефлексия: дневник за 24ч -> JSON (friends_updates/global_lore/behavior_rules)."""
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

        return summary

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
                "friends_updates": [],
                "global_lore": [],
                "behavior_rules": [],
            }

        prompt = (
            "Ты аналитический модуль памяти Нейры. Верни ответ СТРОГО в JSON без пояснений и markdown.\n"
            "Формат:\n"
            "{\n"
            '  "friends_updates": [{"person_hint":"...", "fact":"..."}],\n'
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
                "friends_updates": list(data.get("friends_updates") or []),
                "global_lore": list(data.get("global_lore") or []),
                "behavior_rules": list(data.get("behavior_rules") or [])[:2],
            }
        except Exception as e:
            logger.error("Ошибка LLM-анализа рефлексии: %s", e)
            return {"friends_updates": [], "global_lore": [], "behavior_rules": []}

    @staticmethod
    def _compact_summary(data: dict) -> str:
        fu = len(list(data.get("friends_updates") or []))
        gl = len(list(data.get("global_lore") or []))
        br = len(list(data.get("behavior_rules") or []))
        return f"Self-reflection: friends_updates={fu}, global_lore={gl}, behavior_rules={br}"

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
            if self.diary_hourly_enabled:
                scheduler.add_job(
                    self.hourly_diary_note,
                    trigger="cron",
                    minute=0,
                    id="hourly_diary_note",
                )
            scheduler.start()
            logger.info(f"Рефлексия запланирована на {self.reflection_time} каждую ночь")
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
