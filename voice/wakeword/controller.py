from __future__ import annotations

import logging
from typing import Any


class VoiceController:
    def __init__(self, *, wakeword, recorder, record_seconds: float) -> None:
        self.wakeword = wakeword
        self.recorder = recorder
        self.record_seconds = record_seconds
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
        self.logger.info("录音完成: %s", wav_path if wav_path else "<not saved>")

        self.wakeword.reset()
        self.logger.info("当前不自动恢复唤醒监听，等待上层显式调用")

    def resume_wakeword(self) -> None:
        self.wakeword.reset()
        self.wakeword.resume()
        self.logger.info("已手动恢复唤醒监听")