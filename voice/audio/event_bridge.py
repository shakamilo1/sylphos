from __future__ import annotations

"""Recorder 与 EventBus 的轻量桥接层。

设计意图：
- Recorder 保持“音频数据处理组件”职责，不直接依赖 Runtime 事件模型；
- 由桥接层负责把 `recording.requested` 事件转成 `start_recording` 调用，
  并把录音完成回调转换为 `recording.completed` 事件。
"""

from typing import Any

from sylphos.runtime.events import EventBus, RecordingCompleted, RuntimeEvent
from voice.audio.base import RecorderEngine


class RecorderEventBridge:
    """将 RecorderEngine 接入 EventBus 的适配器。"""

    def __init__(self, *, event_bus: EventBus, recorder: RecorderEngine) -> None:
        self.event_bus = event_bus
        self.recorder = recorder

    def start(self) -> None:
        """启动桥接：订阅录音请求事件并接管录音完成回调。"""
        self.event_bus.subscribe("recording.requested", self._on_recording_requested)
        self.recorder.set_callback(self._on_recorder_callback)

    def stop(self) -> None:
        """停止桥接并解除回调绑定。"""
        self.event_bus.unsubscribe("recording.requested", self._on_recording_requested)
        self.recorder.set_callback(None)

    def _on_recording_requested(self, event: RuntimeEvent) -> None:
        """消费 `recording.requested` 并触发 recorder 开始录音。"""
        duration_seconds = float(event.payload.get("duration_seconds", 0.0))
        self.recorder.start_recording(duration_seconds=duration_seconds)

    def _on_recorder_callback(self, wav_path: str | None, audio_i16: Any, sample_rate: int) -> None:
        """将 Recorder 完成回调转换成统一的 `recording.completed` 事件。"""
        _ = audio_i16
        self.event_bus.publish(RecordingCompleted(wav_path=wav_path, sample_rate=sample_rate))
