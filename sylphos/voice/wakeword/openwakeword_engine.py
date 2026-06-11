from __future__ import annotations

import logging

from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import PauseWakeWordRequested, ResumeWakeWordRequested, WakeWordDetected


class OpenWakeWordEngineAdapter:
    """Adapter wrapping existing voice.wakeword engine without changing detection logic."""
    def __init__(self, event_bus: EventBus, *, audio_hub=None, enabled: bool = False, **kwargs) -> None:
        self.event_bus = event_bus; self.audio_hub = audio_hub; self.enabled = enabled; self.kwargs = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)
        self._engine = None
    def _ensure_engine(self):
        if self._engine is None:
            from voice.wakeword.openwakeword_engine import OpenWakeWordEngine
            self._engine = OpenWakeWordEngine(**self.kwargs)
            self._engine.set_callback(lambda name, score: self.event_bus.publish(WakeWordDetected(name=name, score=score)))
            if self.audio_hub is not None and getattr(self.audio_hub, "_hub", None) is not None:
                self.audio_hub.subscribe(self._engine.consume)
        return self._engine
    def start(self):
        self.event_bus.subscribe("wakeword.pause.requested", self._on_pause)
        self.event_bus.subscribe("wakeword.resume.requested", self._on_resume)
        if self.enabled:
            self._ensure_engine()
        else:
            self.logger.info("WakeWord engine disabled by config; use console 'w' to simulate")
    def _on_pause(self, event): self.pause()
    def _on_resume(self, event): self.resume()
    def pause(self):
        if self._engine: self._engine.pause()
        self.logger.info("Wakeword paused")
    def resume(self):
        if self._engine:
            if hasattr(self._engine, "reset"): self._engine.reset()
            self._engine.resume()
        self.logger.info("Wakeword resumed")
    def stop(self):
        self.event_bus.unsubscribe("wakeword.pause.requested", self._on_pause)
        self.event_bus.unsubscribe("wakeword.resume.requested", self._on_resume)
    def cancel(self): pass
    def close(self): self.stop()
