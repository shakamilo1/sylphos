from __future__ import annotations

import logging
import time

import config
from audio_hub import AudioHub
from command_recorder import CommandRecorder
from controller import VoiceController
from wakeword_consumer import WakeWordConsumer


def _choose_device_from_config():
    if config.AUDIO_INPUT_DEVICE_NAME:
        return config.AUDIO_INPUT_DEVICE_NAME
    return config.AUDIO_INPUT_DEVICE_INDEX


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    hub = AudioHub(
        device=_choose_device_from_config(),
        samplerate=config.INPUT_RATE,
        channels=config.CHANNELS,
        blocksize=config.BLOCKSIZE,
        dtype=config.DTYPE,
    )

    recorder = CommandRecorder(
        input_rate=config.INPUT_RATE,
        save_dir=config.RECORDINGS_DIR,
        save_mode=config.RECORD_SAVE_MODE,
        latest_filename=config.LATEST_RECORD_FILENAME,
        vad_enabled=config.VAD_ENABLED,
        vad_sample_rate=config.VAD_SAMPLE_RATE,
        vad_threshold=config.VAD_THRESHOLD,
        vad_min_speech_duration_ms=config.VAD_MIN_SPEECH_DURATION_MS,
        vad_min_silence_duration_ms=config.VAD_MIN_SILENCE_DURATION_MS,
        vad_speech_pad_ms=config.VAD_SPEECH_PAD_MS,
        vad_end_silence_ms=config.VAD_END_SILENCE_MS,
        vad_prebuffer_ms=config.VAD_PREBUFFER_MS,
        vad_check_interval_ms=config.VAD_CHECK_INTERVAL_MS,
    )

    wake = WakeWordConsumer(
        input_rate=config.INPUT_RATE,
        target_rate=16000,
        threshold=config.WAKEWORD_THRESHOLD,
        cooldown_seconds=config.WAKEWORD_COOLDOWN_SECONDS,
        wakeword_model_source=config.WAKEWORD_MODEL_SOURCE,
        wakeword_model_name=config.WAKEWORD_MODEL_NAME,
        wakeword_model_relative_path=config.WAKEWORD_MODEL_RELATIVE_PATH,
    )

    controller = VoiceController(
        wakeword=wake,
        recorder=recorder,
        record_seconds=config.COMMAND_RECORD_SECONDS,
    )

    wake.on_detect = controller.on_wake_detected
    recorder.on_record_complete = controller.on_record_complete

    hub.subscribe(wake.consume)
    hub.subscribe(recorder.consume)

    hub.start()
    print("AudioHub running. Ctrl+C to stop.")
    print("输入 r + 回车：手动恢复唤醒监听")

    try:
        while True:
            cmd = input().strip().lower()
            if cmd == "r":
                controller.resume_wakeword()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()


if __name__ == "__main__":
    main()