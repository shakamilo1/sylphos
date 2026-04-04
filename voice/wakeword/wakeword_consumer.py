from __future__ import annotations

import importlib.resources as ir
import logging
import math
import time
from pathlib import Path
from typing import Callable

import numpy as np
from openwakeword.model import Model


class WakeWordConsumer:
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

            def _to_16k(x: np.ndarray) -> np.ndarray:
                return resample(
                    x, self.target_rate / self.input_rate, "sinc_fastest"
                ).astype(np.float32)

            self._resample = _to_16k
        except Exception:
            from scipy.signal import resample_poly

            g = math.gcd(int(self.input_rate), int(self.target_rate))
            up = self.target_rate // g
            down = int(self.input_rate) // g

            def _to_16k(x: np.ndarray) -> np.ndarray:
                return resample_poly(x, up, down).astype(np.float32)

            self._resample = _to_16k

        model_kwargs = {
            "inference_framework": "onnx",
        }

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
                model_path = Path(__file__).resolve().parent / model_path
            if not model_path.exists():
                raise FileNotFoundError(f"项目相对模型不存在: {model_path}")
            return model_path

        raise ValueError(f"不支持的模型来源: {source}")

    def pause(self) -> None:
        self._enabled = False
        self._logger.info("唤醒检测已暂停")

    def resume(self) -> None:
        self._enabled = True
        self._logger.info("唤醒检测已恢复")

    def is_enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self._model.reset()
        self._logger.info("wakeword 模型状态已重置")

    def consume(self, audio: np.ndarray) -> None:
        if not self._enabled:
            return

        audio16k = self._resample(audio)
        audio16k_i16 = np.clip(audio16k * 32768.0, -32768, 32767).astype(np.int16)

        scores = self._model.predict(audio16k_i16)
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