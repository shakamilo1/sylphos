from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import ASRResult

_TAG_PATTERN = re.compile(r"<\|[^|]+\|>")
_LANGUAGE_TAG_PATTERN = re.compile(r"<\|(zh|en|yue|ja|ko)\|>", re.IGNORECASE)
_INSTALL_HINT = (
    "缺少 ASR 依赖（funasr / torch / modelscope）。"
    "请先运行：pip install -r requirements-asr.txt"
)


class SenseVoiceEngine:
    def __init__(
        self,
        model: str = "iic/SenseVoiceSmall",
        device: str = "cpu",
        language: str = "auto",
        use_itn: bool = True,
        vad_model: str | None = None,
        disable_update: bool = True,
    ) -> None:
        self.model = model
        self.device = device
        self.language = language
        self.use_itn = use_itn
        self.vad_model = vad_model
        self.disable_update = disable_update
        self._engine: Any | None = None

        self._engine = self._build_model()

    def _build_model(self) -> Any:
        try:
            from funasr import AutoModel
        except Exception as exc:  # pragma: no cover - env dependent
            raise RuntimeError(_INSTALL_HINT) from exc

        kwargs: dict[str, Any] = {
            "model": self.model,
            "device": self.device,
            "disable_update": self.disable_update,
        }
        if self.vad_model:
            kwargs["vad_model"] = self.vad_model

        try:
            return AutoModel(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                "SenseVoice 模型加载失败。可能原因：\n"
                "1) 网络不可用或模型下载被阻断；\n"
                "2) 模型缓存损坏；\n"
                "3) Python / Torch 版本不兼容；\n"
                "4) ModelScope / HuggingFace 访问受限。"
            ) from exc

    def transcribe_file(self, audio_path: str | Path) -> ASRResult:
        path = Path(audio_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")

        result = self._engine.generate(
            input=str(path),
            language=self.language,
            use_itn=self.use_itn,
        )

        parsed = self._parse_result(result)
        raw_text = parsed.get("raw_text")
        tag_language = self._extract_language_from_raw_text(raw_text or "")
        cleaned_text = self._clean_text(raw_text or "")

        metadata = {
            "provider": "sensevoice",
            "model": self.model,
            "device": self.device,
            "use_itn": self.use_itn,
            "raw_result": result,
        }
        if self.vad_model:
            metadata["vad_model"] = self.vad_model

        return ASRResult(
            text=cleaned_text,
            raw_text=raw_text,
            language=tag_language or parsed.get("language") or self.language,
            audio_path=path,
            metadata=metadata,
        )

    def _parse_result(self, result: Any) -> dict[str, Any]:
        language = None
        text = None

        first: Any = result
        if isinstance(result, list) and result:
            first = result[0]

        if isinstance(first, dict):
            text = first.get("text") or first.get("sentence")
            language = first.get("language") or first.get("lang")
        elif isinstance(first, str):
            text = first

        if text is None:
            text = str(first)

        return {"raw_text": str(text), "language": language}

    def _extract_language_from_raw_text(self, raw_text: str) -> str | None:
        match = _LANGUAGE_TAG_PATTERN.search(raw_text)
        if not match:
            return None
        return match.group(1).lower()

    def _clean_text(self, raw_text: str) -> str:
        cleaned = _TAG_PATTERN.sub("", raw_text)
        return " ".join(cleaned.split()).strip()

    def close(self) -> None:
        self._engine = None
