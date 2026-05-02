from __future__ import annotations

"""STT Runtime 事件处理器。

该模块负责把录音事件接入 STT 引擎：
- 监听 `recording.completed` 事件；
- 通过 `create_stt_engine()` 调用具体 STT 实现；
- 发布 `asr.completed` 事件；
- 对异常做保护，确保 EventBus 不因单次识别失败而崩溃。
"""

import logging
from typing import Any

from sylphos.runtime.events import ASRCompleted, EventBus, RuntimeEvent
from sylphos.voice.stt.factory import create_stt_engine


class STTHandler:
    """将 STT 引擎适配到 Runtime EventBus 的处理器。

    Args:
        event_bus: 运行时事件总线实例。
        stt_provider: STT 提供者名称，默认 `sensevoice`。
        stt_kwargs: 传递给 STT 引擎构造器的参数。

    Returns:
        None。
    """

    def __init__(self, *, event_bus: EventBus, stt_provider: str = "sensevoice", **stt_kwargs: Any) -> None:
        self.event_bus = event_bus
        self.stt_provider = stt_provider
        self.stt_kwargs = stt_kwargs
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        """订阅录音完成事件。

        主要逻辑：注册 `recording.completed` 处理函数。
        """
        self.event_bus.subscribe("recording.completed", self._on_recording_completed)

    def stop(self) -> None:
        """取消订阅录音完成事件。"""
        self.event_bus.unsubscribe("recording.completed", self._on_recording_completed)

    def _on_recording_completed(self, event: RuntimeEvent) -> None:
        """消费录音完成事件并执行识别。

        Args:
            event: 运行时事件，期望 payload 中包含 `wav_path`。

        Returns:
            None。处理完成后会发布 `asr.completed` 事件。
        """
        wav_path = event.payload.get("wav_path")
        if not wav_path:
            self.logger.warning("recording.completed 未包含 wav_path，跳过 STT")
            return

        engine = None
        try:
            # 关键节点：通过工厂创建 STT 引擎，便于未来替换 Whisper/其他引擎。
            engine = create_stt_engine(provider=self.stt_provider, **self.stt_kwargs)
            result = engine.transcribe_file(wav_path)

            # 关键节点：发布统一 ASR 事件供上层消费。
            self.event_bus.publish(
                ASRCompleted(
                    audio_path=str(result.audio_path) if result.audio_path else str(wav_path),
                    text=result.text,
                    raw_text=result.raw_text,
                    language=result.language,
                    metadata=result.metadata,
                )
            )
        except Exception:
            # 关键节点：保护事件总线，避免异常向外冒泡导致总线中断。
            self.logger.exception("STTHandler 处理录音事件失败: %s", wav_path)
        finally:
            if engine is not None:
                engine.close()
