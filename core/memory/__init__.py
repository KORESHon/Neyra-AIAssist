"""
core.memory — Memory Hub v2 package.

Hub SQLite (``core.memory.hub.MemoryHub``) is the sole store for people/diary/journal/
working-memory once attached. ``legacy`` only holds thin in-memory helper classes
(``ShortTermMemory``, ``LongTermMemory``/Chroma, ``PeopleDB``, ``NeyraDiary``); there is
no on-disk legacy import path — see docs/adr/0001-memory-hub-v2.md.
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
