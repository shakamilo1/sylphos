from __future__ import annotations
import logging
class DummyTTS:
    def __init__(self) -> None: self.logger = logging.getLogger(self.__class__.__name__)
    def speak(self, text: str) -> None:
        self.logger.info("[DummyTTS] %s", text)
        print(f"🔊 {text}")
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("DummyTTS cancel")
    def close(self): pass
