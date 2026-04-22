from __future__ import annotations

"""wakeword 领域层：OpenWakeWord 的适配实现。

该模块实现了 wakeword 引擎的核心能力（consume/pause/resume/reset），
供 RuntimeOrchestrator 通过统一接口调用。
"""

import importlib.resources as ir
import logging
import math
import time
from pathlib import Path
from typing import Callable

import numpy as np
from openwakeword.model import Model


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class OpenWakeWordEngine:
    """OpenWakeWord 推理引擎适配器。"""

    def __init__(
        self,
        *,
        input_rate: int = 44100,
        target_rate: int = 16000,
        threshold: float = 0.5,
        cooldown_seconds: float = 2.0,
        wakeword_model_source: str = "openwakeword_resource",
        wakeword_model_name: str | None = None,
        wakeword_model_relative_path: str | None = None,
        on_detect: Callable[[str, float], None] | None = None,
    ) -> None:
        self.input_rate = input_rate
        self.target_rate = target_rate
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.on_detect = on_detect

        self._logger = logging.getLogger(self.__class__.__name__)
        self._last_trigger_time = 0.0
        self._last_print_time = 0.0
        self._enabled = True

        try:
            from samplerate import resample

            def _to_target_rate(x: np.ndarray) -> np.ndarray:
                return resample(
                    x, self.target_rate / self.input_rate, "sinc_fastest"
                ).astype(np.float32)

            self._resample = _to_target_rate
        except Exception:
            from scipy.signal import resample_poly

            g = math.gcd(int(self.input_rate), int(self.target_rate))
            up = self.target_rate // g
            down = int(self.input_rate) // g

            def _to_target_rate(x: np.ndarray) -> np.ndarray:
                return resample_poly(x, up, down).astype(np.float32)

            self._resample = _to_target_rate

        model_kwargs = {"inference_framework": "onnx"}

        model_path = self._resolve_model_path(
            source=wakeword_model_source,
            model_name=wakeword_model_name,
            relative_path=wakeword_model_relative_path,
        )
        if model_path is not None:
            model_kwargs["wakeword_models"] = [str(model_path)]

        self._model = Model(**model_kwargs)

    def _resolve_model_path(
        self,
        *,
        source: str,
        model_name: str | None,
        relative_path: str | None,
    ) -> Path | None:
        """解析模型路径。

        - `openwakeword_resource`：从 openwakeword 包内 resources/models 读取；
        - `project_relative`：从项目相对路径加载自定义模型。
        """
        if source == "openwakeword_resource":
            if not model_name:
                return None
            model_dir = Path(str(ir.files("openwakeword") / "resources" / "models"))
            model_path = model_dir / model_name
            if not model_path.exists():
                raise FileNotFoundError(f"openwakeword 资源模型不存在: {model_path}")
            return model_path

        if source == "project_relative":
            if not relative_path:
                raise ValueError("project_relative 模式下必须提供 relative_path")
            model_path = Path(relative_path)
            if not model_path.is_absolute():
                model_path = PROJECT_ROOT / model_path
            if not model_path.exists():
                raise FileNotFoundError(f"项目相对模型不存在: {model_path}")
            return model_path

        raise ValueError(f"不支持的模型来源: {source}")

    def set_callback(self, callback: Callable[[str, float], None]) -> None:
        """注册唤醒命中后的回调，由 RuntimeOrchestrator 注入 EventBus 发布逻辑。"""
        self.on_detect = callback

    def pause(self) -> None:
        """暂停检测（录音阶段调用，防止自激触发）。"""
        self._enabled = False
        self._logger.info("唤醒检测已暂停")

    def resume(self) -> None:
        """恢复检测（手动恢复流程调用）。"""
        self._enabled = True
        self._logger.info("唤醒检测已恢复")

    def is_enabled(self) -> bool:
        """返回当前是否允许执行唤醒检测。"""
        return self._enabled

    def reset(self) -> None:
        """重置 openwakeword 内部状态。"""
        self._model.reset()
        self._logger.info("wakeword 模型状态已重置")

    def close(self) -> None:
        """关闭引擎（当前仅保留日志钩子）。"""
        self._logger.info("OpenWakeWordEngine closed")

    def consume(self, audio: np.ndarray) -> None:
        """消费一段原始音频并进行 wakeword 推理。

        调用链：AudioHub._audio_callback -> OpenWakeWordEngine.consume。
        命中后触发 `on_detect(name, score)`，上层通常将其发布到 EventBus。
        """
        if not self._enabled:
            return

        audio_target = self._resample(audio)
        audio_i16 = np.clip(audio_target * 32768.0, -32768, 32767).astype(np.int16)

        scores = self._model.predict(audio_i16)
        if not scores:
            return

        max_name = max(scores, key=scores.get)
        max_score = float(scores[max_name])

        now = time.time()
        if now - self._last_print_time >= 1.0:
            self._logger.info("[wake max] %s: %.3f", max_name, max_score)
            self._last_print_time = now

        if max_score < self.threshold:
            return

        if now - self._last_trigger_time < self.cooldown_seconds:
            return

        self._last_trigger_time = now
        self._logger.info("🔥 DETECTED: %s score=%.3f", max_name, max_score)

        if self.on_detect:
            self.on_detect(max_name, max_score)


# 兼容旧命名，避免外部调用方短期内中断。
WakeWordConsumer = OpenWakeWordEngine
