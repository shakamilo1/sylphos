from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OpenClawResult:
    """Result returned by Sylphos OpenClaw clients.

    ``raw_text`` preserves the full OpenClaw reply for logs/UI/debugging, while
    ``spoken_text`` is the cleaned and bounded text intended for CosyVoice.
    """

    raw_text: str
    spoken_text: str
    session_key: str
    model: str
    status: str = "ok"
    metadata: dict[str, Any] = field(default_factory=dict)
