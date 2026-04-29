from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ASRResult:
    text: str
    raw_text: str | None = None
    language: str | None = None
    audio_path: Path | None = None
    metadata: dict[str, Any] | None = None


class STTEngine(Protocol):
    def transcribe_file(self, audio_path: str | Path) -> ASRResult:
        ...

    def close(self) -> None:
        ...
