from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass
class TTSResult:
    text: str
    audio_path: Path | None = None
    sample_rate: int | None = None
    provider: str = "cosyvoice"
    metadata: dict[str, Any] | None = None


class TTSEngine(Protocol):
    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path,
        **kwargs: Any,
    ) -> TTSResult:
        ...

    def close(self) -> None:
        ...
