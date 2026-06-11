from __future__ import annotations

import logging

from sylphos.runtime.context import RuntimeContext
from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import ASRCompleted, ASRFailed, ASRRequested


class STTHandler:
    def __init__(self, *, event_bus: EventBus, context: RuntimeContext, engine) -> None:
        self.event_bus = event_bus; self.context = context; self.engine = engine
        self.logger = logging.getLogger(self.__class__.__name__)
    def start(self):
        self.event_bus.subscribe("asr.requested", self._on_asr_requested)
    def stop(self):
        self.event_bus.unsubscribe("asr.requested", self._on_asr_requested)
    def _on_asr_requested(self, event):
        audio_path = getattr(event, "audio_path", None) or self.context.last_audio_path
        try:
            text = self.engine.transcribe(audio_path, self.context)
            self.event_bus.publish(ASRCompleted(audio_path=audio_path, text=text))
        except Exception as exc:
            self.logger.exception("ASR failed")
            self.event_bus.publish(ASRFailed(str(exc), audio_path))
    def pause(self):
        if hasattr(self.engine, "pause"): self.engine.pause()
    def resume(self):
        if hasattr(self.engine, "resume"): self.engine.resume()
    def cancel(self):
        if hasattr(self.engine, "cancel"): self.engine.cancel()
    def close(self):
        self.stop()
        if hasattr(self.engine, "close"): self.engine.close()
