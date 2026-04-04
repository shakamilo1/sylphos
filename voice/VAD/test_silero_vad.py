from __future__ import annotations

import queue
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf
from silero_vad import load_silero_vad, get_speech_timestamps


INPUT_RATE = 16000
CHANNELS = 1
BLOCK_MS = 100              # 每次取 100ms 音频
BLOCK_SIZE = int(INPUT_RATE * BLOCK_MS / 1000)

# 一段话结束后，连续静音多久算结束
END_SILENCE_MS = 800

# 每隔多久做一次 VAD 检测
CHECK_INTERVAL_MS = 200

# 为了避免句首被截断，开始检测到语音时往前补一点缓存
PREBUFFER_MS = 300


def main() -> None:
    print("加载 Silero VAD...")
    model = load_silero_vad()
    print("Silero VAD 已加载")
    print("开始监听。请说话，停顿后会自动结束并保存 wav。Ctrl+C 退出。")

    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    ring_buffer: list[np.ndarray] = []
    prebuffer_blocks = max(1, PREBUFFER_MS // BLOCK_MS)

    recording = False
    recorded_chunks: list[np.ndarray] = []

    last_speech_time = 0.0
    last_check_time = 0.0

    out_dir = Path("vad_test_recordings")
    out_dir.mkdir(parents=True, exist_ok=True)

    def audio_callback(indata, frames, time_info, status):
        if status:
            print(f"[WARN] 音频状态异常: {status}")
        chunk = np.copy(indata[:, 0]).astype(np.float32)
        audio_q.put(chunk)

    with sd.InputStream(
        samplerate=INPUT_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        callback=audio_callback,
    ):
        try:
            while True:
                chunk = audio_q.get()

                ring_buffer.append(chunk)
                if len(ring_buffer) > prebuffer_blocks:
                    ring_buffer.pop(0)

                now = time.time()

                # 正在录音时，先收集音频
                if recording:
                    recorded_chunks.append(chunk)

                # 限制 VAD 检测频率
                if (now - last_check_time) * 1000 < CHECK_INTERVAL_MS:
                    continue
                last_check_time = now

                # 用最近一小段音频做一次检测
                recent_audio = np.concatenate(ring_buffer if not recording else recorded_chunks[-10:], axis=0)
                if recent_audio.size == 0:
                    continue

                speech_ts = get_speech_timestamps(
                    recent_audio,
                    model,
                    sampling_rate=INPUT_RATE,
                    threshold=0.5,
                    min_speech_duration_ms=150,
                    min_silence_duration_ms=300,
                    speech_pad_ms=100,
                )

                has_speech = len(speech_ts) > 0

                if not recording and has_speech:
                    print("[VAD] speech start")
                    recording = True
                    last_speech_time = now
                    recorded_chunks = ring_buffer.copy()

                elif recording:
                    if has_speech:
                        last_speech_time = now
                    else:
                        silence_ms = (now - last_speech_time) * 1000
                        if silence_ms >= END_SILENCE_MS:
                            print("[VAD] speech end")
                            recording = False

                            audio = np.concatenate(recorded_chunks, axis=0)
                            ts = time.strftime("%Y%m%d_%H%M%S")
                            out_path = out_dir / f"vad_segment_{ts}.wav"

                            sf.write(out_path, audio, INPUT_RATE)
                            print(f"[SAVE] {out_path}")

                            recorded_chunks = []
                            ring_buffer = []

        except KeyboardInterrupt:
            print("\n已退出")
if __name__ == "__main__":
    main()            