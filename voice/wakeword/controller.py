from __future__ import annotations

import logging
from typing import Any

from sylphos.runtime.events import EventBus, RecordingCompleted


class VoiceController:
    """唤醒+录音控制器。

    说明：保持 wakeword/recorder/VAD 原有流程不变，
    录音完成后通过 EventBus 发布 `recording.completed`，
    STT 由独立 handler 接管。
    """

    def __init__(self, *, wakeword, recorder, record_seconds: float, event_bus: EventBus | None = None) -> None:
        self.wakeword = wakeword
        self.recorder = recorder
        self.record_seconds = record_seconds
        self.event_bus = event_bus
        self.logger = logging.getLogger(self.__class__.__name__)

    def on_wake_detected(self, name: str, score: float) -> None:
        self.logger.info("收到唤醒事件: %s score=%.3f", name, score)

        self.wakeword.pause()

        self.recorder.start_recording(duration_seconds=self.record_seconds)

        if self.record_seconds > 0:
            self.logger.info("开始录制指令，定时模式 %.1f 秒", self.record_seconds)
        else:
            self.logger.info("开始录制指令，VAD 模式")

    def on_record_complete(
        self,
        wav_path: str | None,
        audio_i16: Any,
        sample_rate: int,
    ) -> None:
        """处理录音结束回调并发布录音完成事件。

        Args:
            wav_path: 录音 wav 文件路径。
            audio_i16: 录音原始 PCM（本层不消费）。
            sample_rate: 录音采样率。

        Returns:
            None。
        """
        self.logger.info("录音完成: %s", wav_path if wav_path else "<not saved>")

        # 关键节点：改为事件驱动 STT，避免控制器与具体 STT 引擎强耦合。
        if self.event_bus is not None:
            self.event_bus.publish(RecordingCompleted(wav_path=wav_path, sample_rate=sample_rate))

        self.wakeword.reset()
        self.logger.info("当前不自动恢复唤醒监听，等待上层显式调用")

    def resume_wakeword(self) -> None:
        self.wakeword.reset()
        self.wakeword.resume()
        self.logger.info("已手动恢复唤醒监听")
