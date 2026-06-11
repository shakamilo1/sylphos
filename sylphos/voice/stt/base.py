from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sylphos.runtime.context import RuntimeContext


@dataclass
class ASRResult:
    text: str
    raw_text: str | None = None
    language: str | None = None
    audio_path: Path | None = None
    metadata: dict[str, Any] | None = None


class STTEngine(Protocol):
    # Existing engine interface.
    def transcribe_file(self, audio_path: str | Path) -> ASRResult: ...
    def close(self) -> None: ...


class RuntimeSTTEngine(Protocol):
    # Runtime adapter interface.
    def transcribe(self, audio_path: str | None, context: RuntimeContext) -> str: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def cancel(self) -> None: ...
    def close(self) -> None: ...


class ASRPostProcessor(Protocol):
    def process(self, text: str, context: RuntimeContext) -> str: ...


class NormalizeTextProcessor:
    def process(self, text: str, context: RuntimeContext) -> str:
        return " ".join(text.strip().replace("，", ",").replace("。", ".").split())


class HotwordCorrectionProcessor:
    def __init__(self, corrections: dict[str, str] | None = None) -> None:
        self.corrections = corrections or {}
    def process(self, text: str, context: RuntimeContext) -> str:
        for src, dst in self.corrections.items():
            text = text.replace(src, dst)
        return text


class CommandAliasProcessor:
    def __init__(self, aliases: dict[str, str] | None = None) -> None:
        self.aliases = aliases or {}
    def process(self, text: str, context: RuntimeContext) -> str:
        stripped = text.strip()
        if stripped in self.aliases:
            return self.aliases[stripped]
        for prefix in ("帮我", "请", "麻烦", "帮忙"):
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip()
        return text


def build_post_processors(config) -> list[ASRPostProcessor]:
    processors: list[ASRPostProcessor] = []
    for name in getattr(config, "ASR_POST_PROCESSORS", []):
        if name == "normalize_text":
            processors.append(NormalizeTextProcessor())
        elif name == "hotword_correction":
            processors.append(HotwordCorrectionProcessor(getattr(config, "HOTWORD_CORRECTIONS", {})))
        elif name == "command_alias":
            processors.append(CommandAliasProcessor(getattr(config, "COMMAND_ALIASES", {})))
    return processors
