from __future__ import annotations

import logging
from dataclasses import dataclass

from sylphos.runtime.event_bus import EventBus


@dataclass
class WakeScoreStatus:
    name: str = ""
    score: float = 0.0
    source: str = ""


class ConsoleFeedback:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.logger = logging.getLogger(self.__class__.__name__)
        self.latest_wake_score = WakeScoreStatus()
        self.latest_state = ""
        self.latest_step = None
        self.latest_event = ""
    def start(self):
        for event_type in (
            "ui.message.requested", "status.changed", "error.occurred", "tts.requested",
            "tool.execution.started", "tool.execution.completed", "tool.execution.failed",
            "wakeword.detected", "wakeword.score.updated",
        ):
            self.event_bus.subscribe(event_type, self._on_event)
    def stop(self):
        for event_type in (
            "ui.message.requested", "status.changed", "error.occurred", "tts.requested",
            "tool.execution.started", "tool.execution.completed", "tool.execution.failed",
            "wakeword.detected", "wakeword.score.updated",
        ):
            self.event_bus.unsubscribe(event_type, self._on_event)
    def _on_event(self, event):
        self.latest_event = event.event_type
        if event.event_type == "ui.message.requested":
            print(f"💬 [{getattr(event, 'level', 'info')}] {getattr(event, 'message', '')}")
        elif event.event_type == "status.changed":
            self.latest_state = getattr(event, "state", "")
            self.latest_step = getattr(event, "step", None)
            print(f"📍 state={getattr(event, 'state', '')} step={getattr(event, 'step', None)}")
        elif event.event_type == "wakeword.score.updated":
            self.latest_wake_score = WakeScoreStatus(
                name=getattr(event, "name", ""),
                score=float(getattr(event, "score", 0.0) or 0.0),
                source=getattr(event, "source", ""),
            )
        elif event.event_type == "wakeword.detected":
            print(f"🔥 wake detected: {getattr(event, 'name', '')} score={float(getattr(event, 'score', 0.0) or 0.0):.3f}")
        elif event.event_type == "error.occurred":
            print(f"❌ {getattr(event, 'error', '')}")
        elif event.event_type == "tts.requested":
            print(f"🗣️ TTSRequested: {getattr(event, 'text', '')}")
        elif event.event_type.startswith("tool.execution"):
            print(f"🛠️ {event.event_type}: {event.payload}")
    def status_lines(self) -> list[str]:
        wake = self.latest_wake_score
        wake_text = f"{wake.name or '-'}  score: {wake.score:.3f}" if wake.name else "-"
        return [
            "Sylphos Runtime",
            f"state: {self.latest_state or '-'}",
            f"wake: {wake_text}",
            f"last_event: {self.latest_event or '-'}",
        ]
    def render_status(self) -> str:
        return "\n".join(self.status_lines())
    def close(self): self.stop()
