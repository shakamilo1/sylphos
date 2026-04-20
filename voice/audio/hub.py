from __future__ import annotations

"""音频采集层：统一管理麦克风输入并分发到多个消费者。

该模块位于 voice.audio 层，不关心具体业务（wakeword/录音/VAD）。
上层在启动阶段创建 :class:`AudioHub`，然后订阅不同 consumer（如唤醒引擎、录音器）。
"""

import logging
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd


AudioCallback = Callable[[np.ndarray], None]


class AudioHub:
    """麦克风输入总线。

    职责：
    1) 打开单个 `sounddevice.InputStream`；
    2) 在音频回调中复制数据并广播给所有订阅者；
    3) 统一处理输入设备解析和生命周期（start/stop）。
    """

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
        """注册音频消费者（按订阅顺序被调用）。"""
        with self._lock:
            self._consumers.append(consumer)

    def unsubscribe(self, consumer: AudioCallback) -> None:
        """取消注册音频消费者。"""
        with self._lock:
            self._consumers = [c for c in self._consumers if c is not consumer]

    def start(self) -> None:
        """启动输入流。

        调用关系：由入口脚本在系统装配完成后调用一次。
        若重复调用会直接返回，不会重复创建 stream。
        """
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
        """停止输入流并释放资源。"""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._logger.info("AudioHub 已停止。")

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice 回调：复制当前音频块并广播给订阅者。

        - `indata` 是本次采样块，默认 shape 为 (frames, channels)。
        - 当前仅取第 0 声道并转成 `float32`，避免消费者间共享同一内存。
        - 任何 consumer 异常都被隔离，避免影响其它 consumer。
        """
        _ = frames, time_info
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
        """将配置中的设备标识解析为 sounddevice 设备索引。

        - `None`：使用系统默认输入设备。
        - `int`：按索引选择，并校验其具备输入通道。
        - `str`：按名称关键字模糊匹配首个输入设备。
        """
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
