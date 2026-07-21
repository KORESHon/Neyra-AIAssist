"""
core.memory — Memory Hub v2 package.

Legacy stores (STM / Chroma LTM / PeopleDB / Diary) live in ``legacy`` during Phase 1A
cutover; new code should prefer ``MemoryHub``.
"""

from __future__ import annotations

from core.memory.hub import MemoryHub
from core.memory.legacy import LongTermMemory, NeyraDiary, PeopleDB, ShortTermMemory
from core.memory.semantic_index import ChromaSemanticIndex, SemanticIndex
from core.memory.sqlite_store import SqliteStore

__all__ = [
    "MemoryHub",
    "SqliteStore",
    "SemanticIndex",
    "ChromaSemanticIndex",
    "ShortTermMemory",
    "LongTermMemory",
    "PeopleDB",
    "NeyraDiary",
]
