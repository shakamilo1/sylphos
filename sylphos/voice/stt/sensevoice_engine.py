from __future__ import annotations

import logging

from sylphos.runtime.context import RuntimeContext


class SenseVoiceEngine:
    """Adapter around the existing sylphos.voice.stt factory/SenseVoice logic."""
    def __init__(self, provider: str = "sensevoice", **kwargs) -> None:
        self.provider = provider
        self.kwargs = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)
        self._engine = None
    def _ensure_engine(self):
        if self._engine is None:
            from sylphos.voice.stt.factory import create_stt_engine
            self._engine = create_stt_engine(provider=self.provider, **self.kwargs)
        return self._engine
    def transcribe(self, audio_path: str | None, context: RuntimeContext) -> str:
        if not audio_path:
            raise ValueError("SenseVoiceEngine requires audio_path")
        result = self._ensure_engine().transcribe_file(audio_path)
        context.extras["last_asr_result"] = result
        return result.text
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("SenseVoiceEngine cancel requested")
    def close(self):
        if self._engine is not None:
            self._engine.close(); self._engine = None
