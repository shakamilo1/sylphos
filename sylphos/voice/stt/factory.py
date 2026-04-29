from __future__ import annotations

from .base import STTEngine
from .sensevoice import SenseVoiceEngine


def create_stt_engine(provider: str = "sensevoice", **kwargs) -> STTEngine:
    normalized = provider.strip().lower()
    if normalized == "sensevoice":
        return SenseVoiceEngine(**kwargs)
    raise ValueError(f"Unsupported STT provider: {provider}")
