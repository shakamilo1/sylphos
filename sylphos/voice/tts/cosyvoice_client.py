from __future__ import annotations

import logging
from pathlib import Path


class CosyVoiceClient:
    """Adapter for the existing CosyVoice clients. Keeps HTTP/SDK details outside runtime."""
    def __init__(self, base_url: str = "http://127.0.0.1:8000", output_path: str = "outputs/tts/latest_tts.wav", **kwargs) -> None:
        self.base_url = base_url; self.output_path = output_path; self.kwargs = kwargs
        self.logger = logging.getLogger(self.__class__.__name__)
        self._engine = None
    def _ensure_engine(self):
        if self._engine is None:
            try:
                from sylphos.voice.tts.factory import create_tts_engine
                self._engine = create_tts_engine(provider="cosyvoice", **self.kwargs)
            except Exception:
                self.logger.exception("Failed to initialize existing CosyVoice engine")
                raise
        return self._engine
    def speak(self, text: str) -> None:
        engine = self._ensure_engine()
        engine.synthesize_to_file(text, Path(self.output_path))
        self.logger.info("CosyVoice synthesized text to %s", self.output_path)
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("CosyVoice cancel requested")
    def close(self):
        if self._engine is not None:
            self._engine.close(); self._engine = None
