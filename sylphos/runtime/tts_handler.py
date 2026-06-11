from __future__ import annotations

import logging

from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import TTSCompleted, TTSRequested, TTSStarted, ErrorOccurred


class TTSHandler:
    def __init__(self, *, event_bus: EventBus, engine) -> None:
        self.event_bus = event_bus; self.engine = engine; self.logger = logging.getLogger(self.__class__.__name__)
    def start(self): self.event_bus.subscribe("tts.requested", self._on_tts_requested)
    def stop(self): self.event_bus.unsubscribe("tts.requested", self._on_tts_requested)
    def _on_tts_requested(self, event):
        text = getattr(event, "text", "") or event.payload.get("text", "")
        if not text: return
        try:
            self.event_bus.publish(TTSStarted(text))
            self.engine.speak(text)
            self.event_bus.publish(TTSCompleted(text=text))
        except Exception as exc:
            self.logger.exception("TTS failed")
            self.event_bus.publish(ErrorOccurred(str(exc), type(exc).__name__, event.event_id, source="tts"))
    def pause(self):
        if hasattr(self.engine, "pause"): self.engine.pause()
    def resume(self):
        if hasattr(self.engine, "resume"): self.engine.resume()
    def cancel(self):
        if hasattr(self.engine, "cancel"): self.engine.cancel()
    def close(self):
        self.stop()
        if hasattr(self.engine, "close"): self.engine.close()
