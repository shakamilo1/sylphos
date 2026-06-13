from __future__ import annotations

import logging

from sylphos.runtime.event_bus import EventBus


class ConsoleFeedback:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.logger = logging.getLogger(self.__class__.__name__)
    def start(self):
        for event_type in ("ui.message.requested", "status.changed", "error.occurred", "tts.requested", "tool.execution.started", "tool.execution.completed", "tool.execution.failed"):
            self.event_bus.subscribe(event_type, self._on_event)
    def stop(self):
        for event_type in ("ui.message.requested", "status.changed", "error.occurred", "tts.requested", "tool.execution.started", "tool.execution.completed", "tool.execution.failed"):
            self.event_bus.unsubscribe(event_type, self._on_event)
    def _on_event(self, event):
        if event.event_type == "ui.message.requested":
            print(f"💬 [{getattr(event, 'level', 'info')}] {getattr(event, 'message', '')}")
        elif event.event_type == "status.changed":
            print(f"📍 state={getattr(event, 'state', '')} step={getattr(event, 'step', None)}")
        elif event.event_type == "error.occurred":
            print(f"❌ {getattr(event, 'error', '')}")
        elif event.event_type == "tts.requested":
            print(f"🗣️ TTSRequested: {getattr(event, 'text', '')}")
        elif event.event_type.startswith("tool.execution"):
            print(f"🛠️ {event.event_type}: {event.payload}")
    def close(self): self.stop()
