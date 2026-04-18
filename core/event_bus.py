"""
Централизованная шина событий ядра Neyra.

Подписчики не должны выполнять тяжёлые или критичные записи в общие хранилища
без собственной синхронизации: ядро сначала фиксирует данные, затем публикует событие.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, DefaultDict

logger = logging.getLogger("neyra.events")

# Согласованные имена для подписчиков / документации
CHAT_TURN_COMPLETED = "chat.turn_completed"
CHAT_TURN_FAILED = "chat.turn_failed"
MEMORY_LONG_TERM_WRITE = "memory.long_term_write"
MEMORY_SHORT_TERM_UPDATE = "memory.short_term_update"
MEMORY_JOURNAL_UPDATED = "memory.journal_updated"
NOTIFY_DISCORD_MESSAGE_SENT = "notify.discord_message_sent"

CoreHandler = Callable[["CoreEvent"], None]


@dataclass(frozen=True)
class CoreEvent:
    """Единый формат события ядра."""

    event_type: str
    source: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Синхронная шина: копия списка обработчиков под локом, вызов снаружи лока."""

    __slots__ = ("_lock", "_by_type", "_wildcard")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_type: DefaultDict[str, list[CoreHandler]] = defaultdict(list)
        self._wildcard: list[CoreHandler] = []

    def subscribe(self, event_type: str, handler: CoreHandler) -> None:
        """Подписка на тип; event_type=\"*\" — все события."""
        with self._lock:
            if event_type == "*":
                self._wildcard.append(handler)
            else:
                self._by_type[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: CoreHandler) -> None:
        with self._lock:
            if event_type == "*":
                self._wildcard = [h for h in self._wildcard if h is not handler]
            else:
                self._by_type[event_type] = [h for h in self._by_type[event_type] if h is not handler]

    def publish(self, event: CoreEvent) -> None:
        to_run: list[CoreHandler]
        with self._lock:
            to_run = list(self._wildcard)
            to_run.extend(self._by_type.get(event.event_type, ()))
        for fn in to_run:
            try:
                fn(event)
            except Exception:
                logger.exception("Event handler failed | type=%s source=%s", event.event_type, event.source)

    def handler_counts(self) -> dict[str, Any]:
        with self._lock:
            return {
                "wildcard": len(self._wildcard),
                "by_type": {k: len(v) for k, v in self._by_type.items() if v},
            }
