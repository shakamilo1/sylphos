from __future__ import annotations

"""TTS Runtime event handler.

The handler keeps text-to-speech as an independent runtime capability:
- subscribe to ``tts.requested``;
- create the configured TTS engine through ``create_tts_engine()``;
- synthesize the requested text to a WAV file;
- publish ``tts.completed`` for downstream playback or UI components;
- catch all synthesis errors so one failed model call never crashes EventBus.
"""

import logging
from pathlib import Path
from typing import Any

from sylphos.runtime.events import EventBus, RuntimeEvent, TTSCompleted
from sylphos.voice.tts.factory import create_tts_engine


class TTSHandler:
    """Adapt a Sylphos TTS engine to the Runtime EventBus.

    This class deliberately does not connect ASR/LLM/TTS into a full dialogue
    chain.  Future orchestration code can publish ``TTSRequested`` after an LLM
    response; this handler only owns the modular synthesis step.
    """

    def __init__(self, *, event_bus: EventBus, tts_provider: str = "cosyvoice", **tts_kwargs: Any) -> None:
        self.event_bus = event_bus
        self.tts_provider = tts_provider
        self.tts_kwargs = tts_kwargs
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        """Subscribe to TTS request events."""
        self.event_bus.subscribe("tts.requested", self._on_tts_requested)

    def stop(self) -> None:
        """Unsubscribe from TTS request events."""
        self.event_bus.unsubscribe("tts.requested", self._on_tts_requested)

    def _on_tts_requested(self, event: RuntimeEvent) -> None:
        """Handle one TTS request event and publish completion.

        Runtime event payload keys:
            text: Required text to synthesize.
            output_path: Required/optional WAV path.  Missing values fall back
                to ``outputs/tts/latest_tts.wav``.
            voice/speaker: Optional speaker hints passed through to CosyVoice.
            prompt_wav/prompt_text: Optional zero-shot prompt inputs passed
                through unchanged for CosyVoice zero-shot synthesis.
        """
        text = str(event.payload.get("text") or "").strip()
        if not text:
            self.logger.warning("tts.requested 未包含 text，跳过 TTS")
            return

        output_path = event.payload.get("output_path") or "outputs/tts/latest_tts.wav"
        speaker = event.payload.get("speaker") or event.payload.get("voice")
        prompt_wav = event.payload.get("prompt_wav")
        prompt_text = event.payload.get("prompt_text")

        engine = None
        try:
            # 关键节点：通过工厂创建 TTS 引擎，使 Runtime 不依赖 CosyVoice 具体实现。
            engine = create_tts_engine(provider=self.tts_provider, **self.tts_kwargs)
            result = engine.synthesize_to_file(
                text,
                Path(output_path),
                speaker=speaker,
                voice=event.payload.get("voice"),
                prompt_wav=prompt_wav,
                prompt_text=prompt_text,
            )

            # 关键节点：发布统一完成事件，下游播放器/UI 只消费 audio_path/sample_rate。
            self.event_bus.publish(
                TTSCompleted(
                    text=result.text,
                    audio_path=str(result.audio_path) if result.audio_path else str(output_path),
                    sample_rate=result.sample_rate,
                    metadata=result.metadata,
                )
            )
        except Exception:
            # 关键节点：保护 EventBus，不让模型加载或推理异常向外冒泡。
            self.logger.exception("TTSHandler 处理 TTS 请求失败: %s", text[:80])
        finally:
            if engine is not None:
                engine.close()
