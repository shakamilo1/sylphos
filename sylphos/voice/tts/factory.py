from __future__ import annotations

from .base import TTSEngine
from .cosyvoice import CosyVoiceEngine


def create_tts_engine(provider: str = "cosyvoice", **kwargs) -> TTSEngine:
    normalized = provider.strip().lower()
    if normalized == "cosyvoice":
        return CosyVoiceEngine(**kwargs)
    raise ValueError(f"Unsupported TTS provider: {provider}")
