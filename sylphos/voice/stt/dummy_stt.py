from __future__ import annotations

import logging

from sylphos.runtime.context import RuntimeContext


class DummySTT:
    def __init__(self, text: str = "打开浏览器") -> None:
        self.text = text
        self.logger = logging.getLogger(self.__class__.__name__)
    def transcribe(self, audio_path: str | None, context: RuntimeContext) -> str:
        self.logger.info("DummySTT transcribe audio_path=%s -> %s", audio_path, self.text)
        return self.text
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("DummySTT cancel")
    def close(self): pass
