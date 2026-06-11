from __future__ import annotations

import logging


class AudioHubAdapter:
    """Adapter around existing voice.audio.hub.AudioHub; can be disabled for headless tests."""
    def __init__(self, *, enabled: bool = False, **kwargs) -> None:
        self.enabled = enabled
        self.kwargs = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)
        self._hub = None
    def _ensure_hub(self):
        if self._hub is None:
            from voice.audio.hub import AudioHub
            self._hub = AudioHub(**self.kwargs)
        return self._hub
    def subscribe(self, consumer):
        self._ensure_hub().subscribe(consumer)
    def unsubscribe(self, consumer):
        if self._hub: self._hub.unsubscribe(consumer)
    def start(self):
        if not self.enabled:
            self.logger.info("AudioHub disabled by config; console/manual events remain available")
            return
        self._ensure_hub().start()
    def stop(self):
        if self._hub: self._hub.stop()
    def pause(self): pass
    def resume(self): pass
    def cancel(self): pass
    def close(self): self.stop()
