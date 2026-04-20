from __future__ import annotations

"""录音组件协议定义。

RecorderEngine 表示“可被 Runtime 编排、可持续消费音频流”的录音能力边界。
其目标是让 Runtime 不依赖具体实现细节（如 CommandRecorder 内部 VAD 逻辑）。
"""

from typing import Callable, Protocol

import numpy as np


RecordCompleteCallback = Callable[[str | None, np.ndarray, int], None]


class RecorderEngine(Protocol):
    """Recorder 组件最小公共接口。"""

    def start_recording(self, duration_seconds: float = 5.0) -> None:
        """请求开始一次录音会话。"""

    def consume(self, audio: np.ndarray) -> None:
        """消费 AudioHub 分发的音频块。"""

    def is_recording(self) -> bool:
        """返回当前是否在录音。"""

    def set_callback(self, callback: RecordCompleteCallback | None) -> None:
        """设置录音完成回调（兼容层/桥接层使用）。"""

    def close(self) -> None:
        """释放录音组件资源。"""
