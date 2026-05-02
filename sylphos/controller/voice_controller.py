from __future__ import annotations

"""VoiceController（事件总线版）。

该控制器保留 wakeword/recorder/VAD 的原有触发行为，
仅把“录音完成后的下一步”改为发布 Runtime 事件，
由独立 STTHandler 执行识别，降低耦合度。
"""

import logging
from typing import Any

from sylphos.runtime.events import EventBus, RecordingCompleted


class VoiceController:
    """语音控制器。

    Args:
        wakeword: 唤醒词引擎实例（需实现 pause/reset/resume）。
        recorder: 录音器实例（需实现 start_recording）。
        event_bus: Runtime 事件总线。
        record_seconds: 录音时长，<=0 表示 VAD 模式。

    Returns:
        None。
    """

    def __init__(self, *, wakeword, recorder, event_bus: EventBus, record_seconds: float) -> None:
        self.wakeword = wakeword
        self.recorder = recorder
        self.event_bus = event_bus
        self.record_seconds = record_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    def on_wake_detected(self, name: str, score: float) -> None:
        """唤醒后启动录音。"""
        self.logger.info("收到唤醒事件: %s score=%.3f", name, score)
        self.wakeword.pause()
        self.recorder.start_recording(duration_seconds=self.record_seconds)

    def on_record_complete(self, wav_path: str | None, audio_i16: Any, sample_rate: int) -> None:
        """录音完成回调。

        Args:
            wav_path: 录音 wav 路径。
            audio_i16: PCM 数据（当前事件链路不直接使用）。
            sample_rate: 采样率。

        Returns:
            None。该方法会发布 `recording.completed` 事件。
        """
        _ = audio_i16
        self.logger.info("录音完成: %s", wav_path if wav_path else "<not saved>")

        # 关键节点：仅发布事件，不在控制器内部直接调用 STT。
        self.event_bus.publish(RecordingCompleted(wav_path=wav_path, sample_rate=sample_rate))

        self.wakeword.reset()
        self.logger.info("当前不自动恢复唤醒监听，等待上层显式调用")

    def resume_wakeword(self) -> None:
        """手动恢复唤醒监听。"""
        self.wakeword.reset()
        self.wakeword.resume()
        self.logger.info("已手动恢复唤醒监听")
