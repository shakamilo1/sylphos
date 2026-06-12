from __future__ import annotations

import sys
import types

import numpy as np

from sylphos.runtime.app import RuntimeApp
from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import RecordingCompleted
from sylphos.voice.audio.recorder import RecorderService


class FakeAudioHub:
    enabled = True

    def __init__(self) -> None:
        self.consumers = []

    def subscribe(self, consumer):
        self.consumers.append(consumer)


def test_recorder_service_uses_legacy_command_recorder_kwargs(monkeypatch, tmp_path):
    calls = []

    class FakeCommandRecorder:
        def __init__(self, **kwargs):
            calls.append(kwargs)
        def consume(self, audio):
            pass

    monkeypatch.setitem(sys.modules, "voice.audio.recorder", types.SimpleNamespace(CommandRecorder=FakeCommandRecorder))
    service = RecorderService(
        EventBus(),
        audio_hub=FakeAudioHub(),
        samplerate=44100,
        output_dir=str(tmp_path),
        channels=1,
        save_mode="latest",
        latest_filename="latest_command.wav",
        vad_enabled=True,
        vad_sample_rate=16000,
        vad_threshold=0.6,
        vad_min_speech_duration_ms=111,
        vad_min_silence_duration_ms=222,
        vad_speech_pad_ms=333,
        vad_end_silence_ms=444,
        vad_prebuffer_ms=555,
        vad_check_interval_ms=666,
    )

    service._ensure_recorder()

    assert calls
    kwargs = calls[0]
    assert "sample_rate" not in kwargs
    assert "output_dir" not in kwargs
    assert kwargs["input_rate"] == 44100
    assert kwargs["save_dir"] == str(tmp_path)
    assert kwargs["vad_threshold"] == 0.6
    assert kwargs["vad_min_speech_duration_ms"] == 111
    assert kwargs["vad_check_interval_ms"] == 666


def test_recorder_service_completion_callback_accepts_legacy_signature():
    bus = EventBus()
    completed = []
    bus.subscribe("recording.completed", completed.append)
    service = RecorderService(bus, samplerate=44100)

    service._on_complete("recordings/latest.wav", np.zeros(10, dtype=np.int16), 16000)

    assert completed
    assert isinstance(completed[-1], RecordingCompleted)
    assert completed[-1].wav_path == "recordings/latest.wav"
    assert completed[-1].sample_rate == 16000


def test_runtime_app_passes_recorder_config_fields():
    config = types.SimpleNamespace(
        AUDIO_ENABLED=True,
        INPUT_RATE=48000,
        CHANNELS=1,
        BLOCKSIZE=4800,
        DTYPE="float32",
        STT_PROVIDER="dummy",
        TTS_PROVIDER="dummy",
        TOOL_EXECUTOR_PROVIDER="dummy",
        OPENCLAW_DRY_RUN=True,
        ASR_POST_PROCESSORS=[],
        WAKEWORD_MODEL_PATH="/tmp/hey_jarvis_v0.1.onnx",
        RECORD_SAVE_DIR="custom_recordings",
        RECORD_SAVE_MODE="archive",
        LATEST_RECORD_FILENAME="latest.wav",
        VAD_ENABLED=False,
        VAD_SAMPLE_RATE=16000,
        VAD_THRESHOLD=0.7,
        VAD_MIN_SPEECH_DURATION_MS=123,
        VAD_MIN_SILENCE_DURATION_MS=234,
        VAD_SPEECH_PAD_MS=345,
        VAD_END_SILENCE_MS=456,
        VAD_PREBUFFER_MS=567,
        VAD_CHECK_INTERVAL_MS=678,
    )

    app = RuntimeApp(config).build()
    recorder = app.registry.get("recorder")

    assert recorder.samplerate == 48000
    assert recorder.output_dir == "custom_recordings"
    assert recorder.save_mode == "archive"
    assert recorder.latest_filename == "latest.wav"
    assert recorder.vad_enabled is False
    assert recorder.vad_threshold == 0.7
    assert recorder.vad_min_speech_duration_ms == 123
    assert recorder.vad_check_interval_ms == 678
