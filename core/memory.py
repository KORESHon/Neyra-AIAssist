"""
core/memory.py — Система памяти Нейры
──────────────────────────────────────
• Краткосрочная: скользящее окно сообщений (in-context)
• Долгосрочная: ChromaDB RAG — векторизованные диалоги
• PeopleDB: JSON-досье на каждого человека
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("neyra.memory")


# ─── Краткосрочная память (история чата) ─────────────────────────────────────

class ShortTermMemory:
    """Скользящее окно сообщений для текущего контекста."""

    def __init__(self, max_messages: int = 10):
        self.max_messages = max_messages
        self._history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]

    def add(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})
        # Обрезаем до max_messages (всегда пары)
        if len(self._history) > self.max_messages:
            self._history = self._history[-self.max_messages:]

    def get_history(self) -> list[dict]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()

    def trim_to_half(self) -> None:
        """Обрезает историю до половины — используется при переполнении контекста."""
        half = max(2, len(self._history) // 2)
        self._history = self._history[-half:]
        logger.info(f"ShortTermMemory обрезана до {len(self._history)} сообщений")

    def __len__(self) -> int:
        return len(self._history)


# ─── Долгосрочная память (ChromaDB RAG) ──────────────────────────────────────

class LongTermMemory:
    """RAG-память на основе ChromaDB + sentence-transformers."""

    def __init__(self, config: dict):
        self.config = config
        mem_cfg = config.get("memory", {})
        self.db_path = mem_cfg.get("chroma_db_path", "./memory/chroma_db")
        self.embedding_model = mem_cfg.get(
            "embedding_model", "paraphrase-multilingual-mpnet-base-v2"
        )
        self.top_k = mem_cfg.get("rag_top_k", 3)
        self.rag_enabled = mem_cfg.get("rag_enabled", True)
        self._collection = None
        self._embedder = None
        self._init_lock = threading.Lock()
        self._initializing = False

        if not self.rag_enabled:
            logger.info("RAG отключён (rag_enabled: false). ChromaDB не загружается.")

    def initialize(self):
        """
        Явная инициализация — вызывай при старте агента.
        Грузит ChromaDB и embedder сразу, а не при первом запросе.
        """
        if not self.rag_enabled:
            return   # Пропускаем — torch/CUDA DLL не загружаются

        with self._init_lock:
            if self._collection is not None:
                return
            if self._initializing:
                return
            self._initializing = True

        try:
            import chromadb
            from chromadb.config import Settings

            # КРИТИЧНО: скрываем GPU от torch ДО его импорта.
            # Иначе torch инициализирует CUDA и занимает pinned memory,
            # из-за чего Ollama не может загрузить модель (resource already mapped).
            import os
            _old_cuda = os.environ.get("CUDA_VISIBLE_DEVICES", None)
            os.environ["CUDA_VISIBLE_DEVICES"] = ""

            from sentence_transformers import SentenceTransformer

            # Восстанавливаем переменную если была
            if _old_cuda is not None:
                os.environ["CUDA_VISIBLE_DEVICES"] = _old_cuda
            else:
                del os.environ["CUDA_VISIBLE_DEVICES"]

            Path(self.db_path).mkdir(parents=True, exist_ok=True)

            client = chromadb.PersistentClient(
                path=self.db_path,
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name="neyra_dialogs",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB: {self.db_path} | {self._collection.count()} записей")

            logger.info(f"Загружаю embedding модель: {self.embedding_model} (CPU only)...")
            self._embedder = SentenceTransformer(self.embedding_model, device="cpu")
            logger.info("Embedding модель загружена ✓ (CPU, без CUDA)")

        except ImportError as e:
            logger.warning(f"ChromaDB/sentence-transformers не установлены: {e}. RAG отключён.")
        except Exception as e:
            logger.error(f"Ошибка инициализации ChromaDB: {e}")
        finally:
            with self._init_lock:
                self._initializing = False

    def initialize_async(self) -> None:
        """Фоновая неблокирующая инициализация RAG/эмбеддера."""
        if not self.rag_enabled:
            return
        with self._init_lock:
            if self._collection is not None or self._initializing:
                return
        threading.Thread(target=self.initialize, name="neyra-rag-init", daemon=True).start()

    def _init(self):
        """Ленивая инициализация — fallback если initialize() не вызвали."""
        self.initialize()

    def save(self, user_msg: str, assistant_msg: str, metadata: Optional[dict] = None) -> None:
        """Сохраняет пару диалога в ChromaDB."""
        self._init()
        if self._collection is None or self._embedder is None:
            return

        try:
            text = f"Пользователь: {user_msg}\nНейра: {assistant_msg}"
            embedding = self._embedder.encode(text, show_progress_bar=False).tolist()
            doc_id = f"dialog_{datetime.now().isoformat()}"

            meta = {"timestamp": datetime.now().isoformat(), "type": "dialog"}
            if metadata:
                meta.update(metadata)

            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[meta],
            )
            logger.debug(f"Диалог сохранён в ChromaDB: {doc_id}")

        except Exception as e:
            logger.error(f"Ошибка сохранения в ChromaDB: {e}")

    def search(self, query: str, n_results: Optional[int] = None) -> list[str]:
        """Ищет похожие диалоги по запросу. Возвращает список текстов."""
        self._init()
        if self._collection is None or self._embedder is None:
            return []

        try:
            k = n_results or self.top_k
            count = self._collection.count()
            if count == 0:
                return []

            k = min(k, count)
            embedding = self._embedder.encode(query, show_progress_bar=False).tolist()
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=k,
            )
            return results["documents"][0] if results["documents"] else []

        except Exception as e:
            logger.error(f"Ошибка поиска в ChromaDB: {e}")
            return []

    def count(self) -> int:
        self._init()
        if self._collection is None:
            return 0
        try:
            return self._collection.count()
        except Exception:
            return 0


# ─── PeopleDB — досье на людей ───────────────────────────────────────────────

class PeopleDB:
    """
    JSON-досье на каждого человека.
    Файлы: memory/people_db/<id>.json
    Идентификация: discord_user_id > ник > имя
    """

    def __init__(self, config: dict):
        mem_cfg = config.get("memory", {})
        base = Path(mem_cfg.get("chroma_db_path", "./memory/chroma_db")).parent
        self.db_dir = base / "people_db"
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Загружает все JSON-файлы в кэш."""
        for f in self.db_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self._cache[data["id"]] = data
            except Exception as e:
                logger.warning(f"Не удалось загрузить {f}: {e}")
        logger.info(f"PeopleDB загружена: {len(self._cache)} записей")

    def _save(self, person_id: str) -> None:
        """Сохраняет досье на диск."""
        if person_id not in self._cache:
            return
        path = self.db_dir / f"{person_id}.json"
        path.write_text(
            json.dumps(self._cache[person_id], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def find(self, identifier: str, discord_id: Optional[str] = None) -> Optional[dict]:
        """Находит досье по discord_id, нику или имени (нечёткий поиск)."""
        identifier_lower = identifier.lower()

        for person in self._cache.values():
            # 1. По Discord ID (приоритет)
            if discord_id and discord_id in person.get("discord_ids", []):
                return person
            # 2. По никам/именам
            names_lower = [n.lower() for n in person.get("names", [])]
            if identifier_lower in names_lower:
                return person
            # 3. Частичное совпадение
            if any(identifier_lower in n or n in identifier_lower for n in names_lower):
                return person

        return None

    def get_all_names_map(self) -> dict[str, str]:
        """Возвращает словарь {ник_нижний_регистр: person_id} для быстрого поиска."""
        result = {}
        for pid, person in self._cache.items():
            for name in person.get("names", []):
                result[name.lower()] = pid
        return result

    def update_fact(self, person_id: str, fact: str) -> bool:
        """Добавляет новый динамический факт о человеке."""
        if person_id not in self._cache:
            logger.warning(f"PeopleDB: человек не найден: {person_id}")
            return False

        entry = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "fact": fact,
        }
        self._cache[person_id].setdefault("dynamic_facts", []).append(entry)
        self._cache[person_id]["last_seen"] = datetime.now().isoformat()
        self._save(person_id)
        logger.info(f"PeopleDB: факт добавлен [{person_id}]: {fact}")
        return True

    def link_discord_id(self, person_id: str, discord_id: str) -> bool:
        """Привязывает Discord User ID к существующему досье."""
        if person_id not in self._cache:
            logger.warning(f"PeopleDB: не найден для привязки: {person_id}")
            return False
        ids = self._cache[person_id].setdefault("discord_ids", [])
        if discord_id not in ids:
            ids.append(discord_id)
            self._save(person_id)
            logger.info(f"PeopleDB: привязан Discord ID {discord_id} → {person_id}")
            return True
        return False  # Уже привязан

    def add_person(self, person_id: str, names: list[str], discord_ids: Optional[list] = None) -> dict:
        """Создаёт новое досье."""
        person = {
            "id": person_id,
            "names": names,
            "discord_ids": discord_ids or [],
            "static_facts": {},
            "dynamic_facts": [],
            "last_seen": datetime.now().isoformat(),
        }
        self._cache[person_id] = person
        self._save(person_id)
        logger.info(f"PeopleDB: создано новое досье [{person_id}]")
        return person

    def get_summary(self, person_id: str) -> str:
        """Возвращает краткое текстовое досье для инжекта в промпт."""
        person = self._cache.get(person_id)
        if not person:
            return ""

        lines = [f"Досье на {person['names'][0]}:"]
        
        # Инжектим Discord ID для правильного пинга
        if person.get("discord_ids") and len(person["discord_ids"]) > 0:
            discord_id = person["discord_ids"][0]
            lines.append(f"  Discord пинг (ИСПОЛЬЗУЙ ЧТОБЫ ТЕГНУТЬ ЕГО): <@{discord_id}>")

        if person.get("static_facts"):
            for k, v in person["static_facts"].items():
                lines.append(f"  {k}: {v}")

        if person.get("dynamic_facts"):
            lines.append("  Новые факты:")
            # Последние 5 фактов
            for fact_entry in person["dynamic_facts"][-5:]:
                lines.append(f"    [{fact_entry['date']}] {fact_entry['fact']}")

        return "\n".join(lines)

    def get_context_for_prompt(self, mentioned_names: list[str]) -> str:
        """
        Принимает список имён упомянутых в запросе,
        возвращает блок с их досье для инжекта в промпт.
        """
        summaries = []
        name_map = self.get_all_names_map()

        for name in mentioned_names:
            pid = name_map.get(name.lower())
            if pid:
                summary = self.get_summary(pid)
                if summary:
                    summaries.append(summary)

        return "\n\n".join(summaries) if summaries else ""
# ─── Личный дневник Нейры ────────────────────────────────────────────────────

class NeyraDiary:
    """Личный дневник Нейры (наблюдения/мысли), хранится в JSONL."""

    def __init__(self, config: dict):
        mem_cfg = config.get("memory", {})
        self.path = Path(mem_cfg.get("diary_path", "./memory/neyra_diary.jsonl"))
        self.max_entries = int(mem_cfg.get("diary_max_entries", 5000))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add_entry(self, text: str, source: str = "manual", meta: Optional[dict] = None) -> bool:
        text = (text or "").strip()
        if not text:
            return False
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "text": text,
            "meta": meta or {},
        }
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._trim_if_needed()
            return True
        except Exception as e:
            logger.error(f"NeyraDiary: ошибка записи: {e}")
            return False

    def _read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows: list[dict] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"NeyraDiary: ошибка чтения: {e}")
        return rows

    def _trim_if_needed(self) -> None:
        rows = self._read_all()
        if len(rows) <= self.max_entries:
            return
        keep = rows[-self.max_entries :]
        self.path.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in keep) + "\n",
            encoding="utf-8",
        )

    def recent(self, limit: int = 10) -> list[dict]:
        rows = self._read_all()
        return rows[-max(1, int(limit)) :]

    def recent_text(self, limit: int = 10) -> str:
        items = self.recent(limit=limit)
        if not items:
            return ""
        lines = []
        for e in items:
            ts = e.get("timestamp", "")
            src = e.get("source", "manual")
            txt = str(e.get("text", "")).strip()
            if txt:
                lines.append(f"[{ts} | {src}] {txt}")
        return "\n".join(lines)
