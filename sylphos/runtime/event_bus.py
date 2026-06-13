from __future__ import annotations

import logging
from threading import RLock
from typing import Callable

from sylphos.runtime.events import ErrorOccurred, RuntimeEvent

EventHandler = Callable[[RuntimeEvent], None]


class EventBus:
    """Small synchronous in-process EventBus with exception isolation."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = RLock()
        self.logger = logging.getLogger(self.__class__.__name__)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            self._handlers[event_type] = [h for h in handlers if h is not handler]
            if not self._handlers.get(event_type):
                self._handlers.pop(event_type, None)

    def publish(self, event: RuntimeEvent) -> None:
        self.logger.debug("publish event_type=%s event_id=%s source=%s", event.event_type, event.event_id, event.source)
        with self._lock:
            handlers = list(self._handlers.get(event.event_type, [])) + list(self._handlers.get("*", []))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                self.logger.exception("event handler failed event_type=%s handler=%r", event.event_type, handler)
                if event.event_type != "error.occurred":
                    self.publish(ErrorOccurred(str(exc), type(exc).__name__, event.event_id, source="event_bus"))
