from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Callable
from uuid import uuid4


@dataclass(slots=True)
class RuntimeEvent:
    """运行时基础事件。"""

    event_type: str
    payload: dict
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class WakeWordDetected(RuntimeEvent):
    name: str = ""
    score: float = 0.0

    def __init__(self, name: str, score: float) -> None:
        super().__init__(
            event_type="wakeword.detected",
            payload={"name": name, "score": score},
        )
        self.name = name
        self.score = score


@dataclass(slots=True)
class RecordingCompleted(RuntimeEvent):
    wav_path: str | None = None
    sample_rate: int = 0

    def __init__(self, wav_path: str | None, sample_rate: int) -> None:
        super().__init__(
            event_type="recording.completed",
            payload={"wav_path": wav_path, "sample_rate": sample_rate},
        )
        self.wav_path = wav_path
        self.sample_rate = sample_rate


EventHandler = Callable[[RuntimeEvent], None]


class EventBus:
    """进程内事件总线。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._lock = RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        with self._lock:
            if event_type not in self._handlers:
                return
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h is not handler]
            if not self._handlers[event_type]:
                self._handlers.pop(event_type, None)

    def publish(self, event: RuntimeEvent) -> None:
        with self._lock:
            handlers = list(self._handlers.get(event.event_type, ()))

        for handler in handlers:
            handler(event)
