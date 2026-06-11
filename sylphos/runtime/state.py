from __future__ import annotations

from enum import StrEnum


class RuntimeState(StrEnum):
    IDLE = "idle"
    WAKEWORD_LISTENING = "wakeword_listening"
    LISTENING = "listening"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    EXECUTING = "executing"
    SPEAKING = "speaking"
    WAITING_CONFIRMATION = "waiting_confirmation"
    ERROR = "error"

    @classmethod
    def coerce(cls, value: str | "RuntimeState") -> "RuntimeState":
        if isinstance(value, cls):
            return value
        return cls(value)
