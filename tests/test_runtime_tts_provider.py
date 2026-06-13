from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sylphos.runtime.app import RuntimeApp
from sylphos.runtime.events import TTSRequested
from sylphos.voice.tts import CosyVoiceClient, DummyTTS, TTSClientRuntimeAdapter


def _config(**overrides):
    data = {
        "AUDIO_ENABLED": False,
        "INPUT_RATE": 44100,
        "AUDIO_SAMPLE_RATE": 44100,
        "CHANNELS": 1,
        "AUDIO_CHANNELS": 1,
        "BLOCKSIZE": 4410,
        "AUDIO_BLOCKSIZE": 4410,
        "DTYPE": "float32",
        "STT_PROVIDER": "dummy",
        "DUMMY_STT_TEXT": "打开浏览器",
        "TTS_PROVIDER": "dummy",
        "TTS_MODEL_VERSION": "base",
        "TTS_VOICE_ID": "official",
        "TTS_TIMEOUT_SECONDS": 240,
        "TTS_AUTO_PLAY": True,
        "TOOL_EXECUTOR_PROVIDER": "dummy",
        "OPENCLAW_DRY_RUN": True,
        "ASR_POST_PROCESSORS": [],
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_tts_provider_base_uses_tts_client_runtime_adapter():
    app = RuntimeApp(_config(TTS_PROVIDER="base")).build()

    engine = app.registry.get("tts").engine

    assert isinstance(engine, TTSClientRuntimeAdapter)
    assert not isinstance(engine, CosyVoiceClient)
    assert engine.model_version == "base"
    assert engine.voice_id == "official"


def test_tts_requested_calls_sylphos_tts_client(monkeypatch):
    calls = []

    class FakeTTSClient:
        def __init__(self, *, model_version, timeout_seconds, auto_play):
            calls.append(("init", model_version, timeout_seconds, auto_play))

        def speak(self, text, *, voice_id):
            calls.append(("speak", text, voice_id))
            return Path("/tmp/sylphos_tts_test.wav")

    import sylphos.voice.tts as tts_module

    monkeypatch.setattr(tts_module, "TTSClient", FakeTTSClient)
    app = RuntimeApp(_config(TTS_PROVIDER="base", TTS_VOICE_ID="Kerrigan")).build()
    completed = []
    errors = []
    app.event_bus.subscribe("tts.completed", completed.append)
    app.event_bus.subscribe("error.occurred", errors.append)

    try:
        app.start()
        app.event_bus.publish(TTSRequested("这是一条测试语音", source="test"))
    finally:
        app.close()

    assert ("init", "base", 240, True) in calls
    assert ("speak", "这是一条测试语音", "Kerrigan") in calls
    assert completed
    assert not errors


def test_tts_provider_dummy_still_uses_dummy_tts():
    app = RuntimeApp(_config(TTS_PROVIDER="dummy")).build()

    assert isinstance(app.registry.get("tts").engine, DummyTTS)


def test_tts_provider_cosyvoice_keeps_cosyvoice_client():
    app = RuntimeApp(_config(TTS_PROVIDER="cosyvoice", COSYVOICE_URL="http://127.0.0.1:8000")).build()

    assert isinstance(app.registry.get("tts").engine, CosyVoiceClient)
