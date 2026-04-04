from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd


AudioCallback = Callable[[np.ndarray], None]


class AudioHub:
    def __init__(
        self,
        *,
        device: int | str | None = None,
        samplerate: int = 44100,
        channels: int = 1,
        blocksize: int = 4410,
        dtype: str = "float32",
    ) -> None:
        self.device = device
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.dtype = dtype

        self._logger = logging.getLogger(self.__class__.__name__)
        self._stream: Optional[sd.InputStream] = None
        self._consumers: list[AudioCallback] = []
        self._lock = threading.Lock()

    def subscribe(self, consumer: AudioCallback) -> None:
        with self._lock:
            self._consumers.append(consumer)

    def unsubscribe(self, consumer: AudioCallback) -> None:
        with self._lock:
            self._consumers = [c for c in self._consumers if c is not consumer]

    def start(self) -> None:
        if self._stream is not None:
            self._logger.warning("AudioHub 已启动。")
            return

        selected_device = self._resolve_input_device(self.device)
        if selected_device is None:
            self._logger.info("使用系统默认输入设备。")
        else:
            dev = sd.query_devices(selected_device)
            self._logger.info(
                "使用输入设备: [%s] %s | default_sr=%s",
                selected_device,
                dev["name"],
                dev["default_samplerate"],
            )

        self._stream = sd.InputStream(
            device=selected_device,
            samplerate=self.samplerate,
            channels=self.channels,
            blocksize=self.blocksize,
            dtype=self.dtype,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._logger.info("AudioHub 已启动。")

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._logger.info("AudioHub 已停止。")

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            self._logger.warning("音频流状态异常: %s", status)

        audio = np.copy(indata[:, 0]).astype(np.float32)

        with self._lock:
            consumers = list(self._consumers)

        for consumer in consumers:
            try:
                consumer(audio)
            except Exception:
                self._logger.exception("Audio consumer 执行失败")

    def _resolve_input_device(self, device: int | str | None) -> int | None:
        if device is None:
            return None

        devices = sd.query_devices()

        if isinstance(device, int):
            dev = devices[device]
            if dev["max_input_channels"] > 0:
                return device
            raise ValueError(f"设备 {device} 不是输入设备。")

        if isinstance(device, str):
            keyword = device.strip().lower()
            for idx, dev in enumerate(devices):
                if dev["max_input_channels"] > 0 and keyword in dev["name"].lower():
                    return idx
            self._logger.warning("未按名称匹配到输入设备: %s，回退到系统默认。", device)
            return None

        return None