from __future__ import annotations

import logging

from sylphos.runtime.events import (
    EventBus,
    RecordingCompleted,
    RecordingRequested,
    RuntimeEvent,
    WakeWordDetected,
)
from voice.wakeword.base import WakeWordEngine


class RuntimeOrchestrator:
    """运行时事件编排器。

    角色定位：
    - 监听 wakeword/recording 语义事件；
    - 发布录音请求事件，而非直接操控具体 Recorder 实现；
    - 维护唤醒状态切换策略（pause/reset/resume）。
    """

    def __init__(
        self,
        *,
        event_bus: EventBus,
        wakeword_engine: WakeWordEngine,
        record_seconds: float,
    ) -> None:
        self.event_bus = event_bus
        self.wakeword_engine = wakeword_engine
        self.record_seconds = record_seconds
        self.logger = logging.getLogger(self.__class__.__name__)

    def start(self) -> None:
        """注册事件处理器并接入 wakeword 回调。"""
        self.event_bus.subscribe("wakeword.detected", self._on_wakeword_detected)
        self.event_bus.subscribe("recording.completed", self._on_recording_completed)

        self.wakeword_engine.set_callback(
            lambda name, score: self.event_bus.publish(WakeWordDetected(name=name, score=score))
        )

    def stop(self) -> None:
        """注销事件处理器。"""
        self.event_bus.unsubscribe("wakeword.detected", self._on_wakeword_detected)
        self.event_bus.unsubscribe("recording.completed", self._on_recording_completed)

    def _on_wakeword_detected(self, event: RuntimeEvent) -> None:
        """唤醒命中后发布录音请求事件。"""
        payload = event.payload
        self.logger.info(
            "收到唤醒事件: %s score=%.3f",
            payload.get("name", "unknown"),
            payload.get("score", 0.0),
        )

        # 先暂停唤醒，避免录音过程再次触发 wakeword。
        self.wakeword_engine.pause()

        # 录音开始由事件驱动：桥接层接收 recording.requested 后启动 Recorder。
        self.event_bus.publish(RecordingRequested(duration_seconds=self.record_seconds))

        if self.record_seconds > 0:
            self.logger.info("开始录制指令，定时模式 %.1f 秒", self.record_seconds)
        else:
            self.logger.info("开始录制指令，VAD 模式")

    def _on_recording_completed(self, event: RuntimeEvent) -> None:
        """录音完成后维护 wakeword 生命周期策略。"""
        self.logger.info("录音完成: %s", event.payload.get("wav_path") or "<not saved>")
        self.wakeword_engine.reset()
        self.logger.info("当前不自动恢复唤醒监听，等待上层显式调用")

    def resume_wakeword(self) -> None:
        """手动恢复唤醒监听（保留现有交互行为）。"""
        self.wakeword_engine.reset()
        self.wakeword_engine.resume()
        self.logger.info("已手动恢复唤醒监听")
