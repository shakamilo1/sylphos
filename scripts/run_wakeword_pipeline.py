from __future__ import annotations

"""Wakeword 运行入口。

本文件同时装配两条“并行但互补”的流：

1) 音频流（AudioHub）：
   负责采集麦克风原始音频帧，并把高频音频块分发给 wakeword 与 recorder 消费。

2) 事件流（EventBus）：
   负责低频语义事件编排，串联 wakeword.detected -> recording.requested
   -> recording.completed 的控制链路。

主装配关系如下：
1) EventBus：承载 wakeword.detected / recording.requested / recording.completed 事件；
2) AudioHub：采集麦克风并广播音频帧；
3) OpenWakeWordEngine：消费音频帧并在命中时触发唤醒回调；
4) CommandRecorder：执行定时录音或 VAD 录音；
5) RecorderEventBridge：把 RecorderEngine API 与 EventBus 对接；
6) RuntimeOrchestrator：负责事件编排以及 pause/reset/resume 等策略控制。

推荐运行方式：
- `python -m scripts.run_wakeword_pipeline`
- 或 `python scripts/run_wakeword_pipeline.py`
"""

import logging

from config import voice as voice_config
from sylphos.runtime.events import EventBus
from sylphos.runtime.orchestrator import RuntimeOrchestrator
from voice.audio.event_bridge import RecorderEventBridge
from voice.audio.hub import AudioHub
from voice.audio.recorder import CommandRecorder
from voice.wakeword.openwakeword_engine import OpenWakeWordEngine


def _choose_device_from_config() -> int | str | None:
    """优先按设备名匹配，未配置时回退到设备索引。"""
    if voice_config.AUDIO_INPUT_DEVICE_NAME:
        return voice_config.AUDIO_INPUT_DEVICE_NAME
    return voice_config.AUDIO_INPUT_DEVICE_INDEX


def main() -> None:
    """组装并启动 wakeword + recorder 的事件化运行链路。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    # 事件流组件：负责编排 wakeword / recorder 之间的语义事件。
    event_bus = EventBus()

    # 音频流组件：负责把麦克风原始音频分发给多个消费者。
    hub = AudioHub(
        device=_choose_device_from_config(),
        samplerate=voice_config.INPUT_RATE,
        channels=voice_config.CHANNELS,
        blocksize=voice_config.BLOCKSIZE,
        dtype=voice_config.DTYPE,
    )

    # 具体能力组件：一个负责唤醒词检测，一个负责录音。
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

    # 编排层：只处理事件与策略，不直接依赖 Recorder 的具体实现细节。
    orchestrator = RuntimeOrchestrator(
        event_bus=event_bus,
        wakeword_engine=wake,
        record_seconds=voice_config.COMMAND_RECORD_SECONDS,
    )

    # Bridge 层：负责把 recording.requested / recording.completed 与 Recorder API 对接。
    recorder_bridge = RecorderEventBridge(event_bus=event_bus, recorder=recorder)

    orchestrator.start()
    recorder_bridge.start()

    # AudioHub 负责高频音频流，EventBus 负责低频控制流，两者并行协作。
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
        recorder_bridge.stop()
        orchestrator.stop()
        recorder.close()
        wake.close()


if __name__ == "__main__":
    main()