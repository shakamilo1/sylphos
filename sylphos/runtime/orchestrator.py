from __future__ import annotations

import logging
from typing import Any

from sylphos.runtime.events import EventBus, RecordingCompleted, RuntimeEvent, WakeWordDetected


class RuntimeOrchestrator:
    """将语音链路从“直连”升级到事件驱动编排。"""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        wakeword_engine: Any,
        recorder_service: Any,
        record_seconds: float,
    ) -> None:
        self.event_bus = event_bus
        self.wakeword_engine = wakeword_engine
        self.recorder_service = recorder_service
        self.record_seconds = record_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        self.event_bus.subscribe("wakeword.detected", self._on_wakeword_detected)
        self.event_bus.subscribe("recording.completed", self._on_recording_completed)

        self.wakeword_engine.set_callback(
            lambda name, score: self.event_bus.publish(WakeWordDetected(name=name, score=score))
        )
        self.recorder_service.on_record_complete = self._on_recorder_callback

    def stop(self) -> None:
        self.event_bus.unsubscribe("wakeword.detected", self._on_wakeword_detected)
        self.event_bus.unsubscribe("recording.completed", self._on_recording_completed)

    def _on_recorder_callback(self, wav_path: str | None, audio_i16: Any, sample_rate: int) -> None:
        _ = audio_i16
        self.event_bus.publish(RecordingCompleted(wav_path=wav_path, sample_rate=sample_rate))

    def _on_wakeword_detected(self, event: RuntimeEvent) -> None:
        payload = event.payload
        self.logger.info(
            "收到唤醒事件: %s score=%.3f",
            payload.get("name", "unknown"),
            payload.get("score", 0.0),
        )
        self.wakeword_engine.pause()
        self.recorder_service.start_recording(duration_seconds=self.record_seconds)

        if self.record_seconds > 0:
            self.logger.info("开始录制指令，定时模式 %.1f 秒", self.record_seconds)
        else:
            self.logger.info("开始录制指令，VAD 模式")

    def _on_recording_completed(self, event: RuntimeEvent) -> None:
        self.logger.info("录音完成: %s", event.payload.get("wav_path") or "<not saved>")
        self.wakeword_engine.reset()
        self.logger.info("当前不自动恢复唤醒监听，等待上层显式调用")

    def resume_wakeword(self) -> None:
        self.wakeword_engine.reset()
        self.wakeword_engine.resume()
        self.logger.info("已手动恢复唤醒监听")
