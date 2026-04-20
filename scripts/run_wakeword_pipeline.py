from __future__ import annotations

"""Wakeword 运行入口。

装配关系（main 中完成）：
1) EventBus：承载 wakeword.detected / recording.completed 事件；
2) AudioHub：采集麦克风并广播音频帧；
3) OpenWakeWordEngine：消费音频帧并在命中时回调；
4) CommandRecorder：在 orchestrator 触发后执行定时或 VAD 录音；
5) RuntimeOrchestrator：订阅/发布事件并串联 pause/reset/resume 流程。

推荐运行方式：
- `python -m scripts.run_wakeword_pipeline`
- 或 `python scripts/run_wakeword_pipeline.py`
"""

import logging

from config import voice as voice_config
from sylphos.runtime.events import EventBus
from sylphos.runtime.orchestrator import RuntimeOrchestrator
from voice.audio.hub import AudioHub
from voice.audio.recorder import CommandRecorder
from voice.wakeword.openwakeword_engine import OpenWakeWordEngine


def _choose_device_from_config() -> int | str | None:
    """优先按设备名匹配，未配置时回退到设备索引。"""
    if voice_config.AUDIO_INPUT_DEVICE_NAME:
        return voice_config.AUDIO_INPUT_DEVICE_NAME
    return voice_config.AUDIO_INPUT_DEVICE_INDEX


def main() -> None:
    """组装并启动整条 wakeword -> record 管线。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    event_bus = EventBus()

    hub = AudioHub(
        device=_choose_device_from_config(),
        samplerate=voice_config.INPUT_RATE,
        channels=voice_config.CHANNELS,
        blocksize=voice_config.BLOCKSIZE,
        dtype=voice_config.DTYPE,
    )

    recorder = CommandRecorder(
        input_rate=voice_config.INPUT_RATE,
        save_dir=voice_config.RECORDINGS_DIR,
        save_mode=voice_config.RECORD_SAVE_MODE,
        latest_filename=voice_config.LATEST_RECORD_FILENAME,
        vad_enabled=voice_config.VAD_ENABLED,
        vad_sample_rate=voice_config.VAD_SAMPLE_RATE,
        vad_threshold=voice_config.VAD_THRESHOLD,
        vad_min_speech_duration_ms=voice_config.VAD_MIN_SPEECH_DURATION_MS,
        vad_min_silence_duration_ms=voice_config.VAD_MIN_SILENCE_DURATION_MS,
        vad_speech_pad_ms=voice_config.VAD_SPEECH_PAD_MS,
        vad_end_silence_ms=voice_config.VAD_END_SILENCE_MS,
        vad_prebuffer_ms=voice_config.VAD_PREBUFFER_MS,
        vad_check_interval_ms=voice_config.VAD_CHECK_INTERVAL_MS,
    )

    wake = OpenWakeWordEngine(
        input_rate=voice_config.INPUT_RATE,
        target_rate=16000,
        threshold=voice_config.WAKEWORD_THRESHOLD,
        cooldown_seconds=voice_config.WAKEWORD_COOLDOWN_SECONDS,
        wakeword_model_source=voice_config.WAKEWORD_MODEL_SOURCE,
        wakeword_model_name=voice_config.WAKEWORD_MODEL_NAME,
        wakeword_model_relative_path=voice_config.WAKEWORD_MODEL_RELATIVE_PATH,
    )

    orchestrator = RuntimeOrchestrator(
        event_bus=event_bus,
        wakeword_engine=wake,
        recorder_service=recorder,
        record_seconds=voice_config.COMMAND_RECORD_SECONDS,
    )
    orchestrator.start()

    # AudioHub 与业务组件通过订阅耦合：同一音频流同时喂给 wakeword 和 recorder。
    hub.subscribe(wake.consume)
    hub.subscribe(recorder.consume)

    hub.start()
    print("AudioHub running. Ctrl+C to stop.")
    print("输入 r + 回车：手动恢复唤醒监听")

    try:
        while True:
            cmd = input().strip().lower()
            if cmd == "r":
                orchestrator.resume_wakeword()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        orchestrator.stop()
        wake.close()


if __name__ == "__main__":
    main()
