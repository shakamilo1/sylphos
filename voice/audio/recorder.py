from __future__ import annotations

"""录音服务层：消费 AudioHub 的音频流并在指令结束时产出 WAV。

该模块位于 voice.audio 层，支持两种结束策略：
1) 定时模式（固定秒数）；
2) VAD 模式（检测到说话结束后自动收尾）。

录音完成后通过回调通知上层；当前主流程建议通过 EventBus 桥接该回调。
"""

import threading
import time
import wave
from pathlib import Path
import logging

import numpy as np

from voice.audio.base import RecordCompleteCallback, RecorderEngine


class CommandRecorder(RecorderEngine):
    """RecorderEngine 的默认实现。

    - 保留 timed / VAD 两种录音结束策略；
    - 保留 on_record_complete 兼容回调；
    - 推荐由 Recorder 事件桥接层把回调转换成 `recording.completed` 事件。
    """

    def __init__(
        self,
        *,
        input_rate: int = 44100,
        save_dir: str = "recordings",
        channels: int = 1,
        sample_width_bytes: int = 2,
        on_record_complete: RecordCompleteCallback | None = None,
        save_mode: str = "latest",  # off / latest / archive
        latest_filename: str = "latest_command.wav",
        vad_enabled: bool = True,
        vad_sample_rate: int = 16000,
        vad_threshold: float = 0.5,
        vad_min_speech_duration_ms: int = 150,
        vad_min_silence_duration_ms: int = 300,
        vad_speech_pad_ms: int = 100,
        vad_end_silence_ms: int = 800,
        vad_prebuffer_ms: int = 300,
        vad_check_interval_ms: int = 200,
    ) -> None:
        self.input_rate = input_rate
        self.save_dir = Path(save_dir)
        self.channels = channels
        self.sample_width_bytes = sample_width_bytes
        self.on_record_complete = on_record_complete
        self.save_mode = save_mode
        self.latest_filename = latest_filename

        self.vad_enabled = vad_enabled
        self.vad_sample_rate = vad_sample_rate
        self.vad_threshold = vad_threshold
        self.vad_min_speech_duration_ms = vad_min_speech_duration_ms
        self.vad_min_silence_duration_ms = vad_min_silence_duration_ms
        self.vad_speech_pad_ms = vad_speech_pad_ms
        self.vad_end_silence_ms = vad_end_silence_ms
        self.vad_prebuffer_ms = vad_prebuffer_ms
        self.vad_check_interval_ms = vad_check_interval_ms

        self._lock = threading.Lock()
        self._recording = False
        self._mode = "timed"  # timed / vad

        self._buffers: list[np.ndarray] = []
        self._record_until = 0.0

        # VAD 运行时状态
        self._vad_model = None
        self._vad_ring_buffer: list[np.ndarray] = []
        self._vad_speech_started = False
        self._vad_last_speech_time = 0.0
        self._vad_last_check_time = 0.0

        self._logger = logging.getLogger(self.__class__.__name__)
        self.save_dir.mkdir(parents=True, exist_ok=True)


    def set_callback(self, callback: RecordCompleteCallback | None) -> None:
        """设置录音完成回调。

        该方法用于统一 RecorderEngine 接口风格；
        内部仍复用 `on_record_complete` 字段以兼容已有调用。
        """
        self.on_record_complete = callback

    def is_recording(self) -> bool:
        """当前是否处于录音状态。"""
        with self._lock:
            return self._recording

    def start_recording(self, duration_seconds: float = 5.0) -> None:
        """开始一次新的录音会话。

        - `duration_seconds > 0`：固定时长录音（timed）。
        - `duration_seconds <= 0`：进入 VAD 自动结束模式（vad）。
        """
        with self._lock:
            self._buffers = []
            self._recording = True

            # 每次新录音都重置 VAD 状态，避免旧会话污染。
            self._vad_ring_buffer = []
            self._vad_speech_started = False
            self._vad_last_speech_time = 0.0
            self._vad_last_check_time = 0.0

            if duration_seconds > 0:
                self._mode = "timed"
                self._record_until = time.time() + duration_seconds
                print(f"[REC] timed mode: {duration_seconds:.1f}s")
            else:
                if not self.vad_enabled:
                    raise RuntimeError("COMMAND_RECORD_SECONDS <= 0，但 VAD 未启用")
                self._mode = "vad"
                self._record_until = 0.0
                self._ensure_vad_loaded()
                print("[REC] vad mode")

    def consume(self, audio: np.ndarray) -> None:
        """接收 AudioHub 分发的音频块并按当前模式处理。"""
        with self._lock:
            if not self._recording:
                return
            mode = self._mode

        if mode == "timed":
            self._consume_timed(audio)
        else:
            self._consume_vad(audio)

    def _consume_timed(self, audio: np.ndarray) -> None:
        """固定时长录音：持续缓存直到达到结束时间。"""
        should_save = False

        with self._lock:
            if not self._recording:
                return

            self._buffers.append(np.copy(audio))

            # 到达截止时间后结束本次录音并触发保存。
            if time.time() >= self._record_until:
                self._recording = False
                should_save = True

        if should_save:
            self._save_wav()

    def _consume_vad(self, audio: np.ndarray) -> None:
        """VAD 模式：检测“开始说话/说话结束”并控制录音生命周期。"""
        now = time.time()
        chunk = np.copy(audio)

        with self._lock:
            if not self._recording:
                return

            # 预缓冲：保留最近一段音频，防止句首被裁切。
            self._vad_ring_buffer.append(chunk)
            prebuffer_blocks = max(
                1,
                int(
                    self.vad_prebuffer_ms
                    / max(1, len(chunk) * 1000 / self.input_rate)
                ),
            )
            if len(self._vad_ring_buffer) > prebuffer_blocks:
                self._vad_ring_buffer.pop(0)

            # 一旦进入“已说话”状态，后续音频都应落盘。
            if self._vad_speech_started:
                self._buffers.append(chunk)

            # 降低 VAD 计算频率，避免每个 chunk 都做重采样和推理。
            if (now - self._vad_last_check_time) * 1000 < self.vad_check_interval_ms:
                return

            self._vad_last_check_time = now
            recent_audio = (
                np.concatenate(self._buffers[-10:], axis=0)
                if self._vad_speech_started and self._buffers
                else np.concatenate(self._vad_ring_buffer, axis=0)
            )

        # VAD 推理统一在 16k 采样率上完成。
        audio_16k = self._resample_to_vad_rate(recent_audio)
        has_speech = self._has_speech(audio_16k)

        should_save = False

        with self._lock:
            if not self._recording:
                return

            if not self._vad_speech_started and has_speech:
                # 首次检测到语音时，把预缓冲一起纳入正式录音。
                self._vad_speech_started = True
                self._vad_last_speech_time = now
                self._buffers = list(self._vad_ring_buffer)
                print("[VAD] speech start")
                return

            if self._vad_speech_started:
                if has_speech:
                    self._vad_last_speech_time = now
                else:
                    silence_ms = (now - self._vad_last_speech_time) * 1000
                    # 静音持续达到阈值，判定说话结束并收尾保存。
                    if silence_ms >= self.vad_end_silence_ms:
                        self._recording = False
                        should_save = True
                        print("[VAD] speech end")

        if should_save:
            self._save_wav()

    def _ensure_vad_loaded(self) -> None:
        """懒加载 Silero VAD 模型，仅在 VAD 模式首次使用时初始化。"""
        if self._vad_model is not None:
            return

        from silero_vad import load_silero_vad

        self._vad_model = load_silero_vad()

    def _resample_to_vad_rate(self, audio: np.ndarray) -> np.ndarray:
        """将输入音频重采样到 VAD 采样率（默认 16k）。"""
        if self.input_rate == self.vad_sample_rate:
            return audio.astype(np.float32)

        try:
            from samplerate import resample

            ratio = self.vad_sample_rate / self.input_rate
            return resample(audio, ratio, "sinc_fastest").astype(np.float32)
        except Exception:
            from scipy.signal import resample_poly
            import math

            g = math.gcd(int(self.input_rate), int(self.vad_sample_rate))
            up = self.vad_sample_rate // g
            down = self.input_rate // g
            return resample_poly(audio, up, down).astype(np.float32)

    def _has_speech(self, audio_16k: np.ndarray) -> bool:
        """执行 VAD 检测并返回当前片段是否包含语音。"""
        if audio_16k.size == 0:
            return False

        from silero_vad import get_speech_timestamps

        speech_ts = get_speech_timestamps(
            audio_16k,
            self._vad_model,
            sampling_rate=self.vad_sample_rate,
            threshold=self.vad_threshold,
            min_speech_duration_ms=self.vad_min_speech_duration_ms,
            min_silence_duration_ms=self.vad_min_silence_duration_ms,
            speech_pad_ms=self.vad_speech_pad_ms,
        )
        return len(speech_ts) > 0

    def _save_wav(self) -> None:
        """保存缓冲音频并触发录音完成回调。"""
        with self._lock:
            if not self._buffers:
                return
            audio = np.concatenate(self._buffers, axis=0)
            self._buffers = []
            self._vad_ring_buffer = []
            self._vad_speech_started = False
            self._vad_last_speech_time = 0.0
            self._vad_last_check_time = 0.0

        audio_i16 = np.clip(audio * 32768.0, -32768, 32767).astype(np.int16)

        if self.save_mode == "off":
            if self.on_record_complete:
                self.on_record_complete(None, audio_i16, self.input_rate)
            return

        if self.save_mode == "latest":
            out_path = self.save_dir / self.latest_filename
        elif self.save_mode == "archive":
            ts = time.strftime("%Y%m%d_%H%M%S")
            out_path = self.save_dir / f"command_{ts}.wav"
        else:
            raise ValueError(f"未知 save_mode: {self.save_mode}")

        with wave.open(str(out_path), "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width_bytes)
            wf.setframerate(self.input_rate)
            wf.writeframes(audio_i16.tobytes())

        print(f"[REC] saved: {out_path}")

        if self.on_record_complete:
            self.on_record_complete(str(out_path), audio_i16, self.input_rate)

    def close(self) -> None:
        """关闭录音器。

        当前实现没有外部句柄需要释放，保留该方法用于协议一致性与未来扩展。
        """
        self._logger.info("CommandRecorder closed")
