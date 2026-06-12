from __future__ import annotations

from types import SimpleNamespace

from sylphos.runtime.app import RuntimeApp
from sylphos.voice.wakeword.openwakeword_engine import OpenWakeWordEngineAdapter


def _runtime_config(**overrides):
    values = {
        "AUDIO_ENABLED": False,
        "INPUT_RATE": 44100,
        "CHANNELS": 1,
        "BLOCKSIZE": 4410,
        "DTYPE": "float32",
        "STT_PROVIDER": "dummy",
        "TTS_PROVIDER": "dummy",
        "TOOL_EXECUTOR_PROVIDER": "dummy",
        "OPENCLAW_DRY_RUN": True,
        "ASR_POST_PROCESSORS": [],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_runtime_app_passes_explicit_wakeword_model_path(tmp_path):
    model = tmp_path / "hey_jarvis_v0.1.onnx"
    model.write_bytes(b"dummy")

    app = RuntimeApp(
        _runtime_config(
            AUDIO_ENABLED=True,
            WAKEWORD_MODEL_PATH=str(model),
            WAKEWORD_MODEL_NAME="ignored.onnx",
            WAKEWORD_MODEL_SOURCE="openwakeword_resource",
        )
    ).build()

    wakeword = app.registry.get("wakeword")
    assert wakeword.enabled is True
    assert wakeword.kwargs["wakeword_model_source"] == "project_relative"
    assert wakeword.kwargs["wakeword_model_relative_path"] == str(model)
    assert wakeword.kwargs["wakeword_model_name"] == "ignored.onnx"


def test_runtime_app_combines_wakeword_model_dir_and_name():
    app = RuntimeApp(
        _runtime_config(
            AUDIO_ENABLED=True,
            WAKEWORD_MODEL_SOURCE="project_relative",
            WAKEWORD_MODEL_DIR="models/wakeword",
            WAKEWORD_MODEL_NAME="hey_jarvis_v0.1.onnx",
        )
    ).build()

    wakeword = app.registry.get("wakeword")
    assert wakeword.kwargs["wakeword_model_source"] == "project_relative"
    assert wakeword.kwargs["wakeword_model_relative_path"].replace("\\", "/") == "models/wakeword/hey_jarvis_v0.1.onnx"
    assert wakeword.kwargs["wakeword_model_name"] == "hey_jarvis_v0.1.onnx"


def test_audio_disabled_does_not_initialize_wakeword_model(monkeypatch):
    def fail_if_called(self):  # pragma: no cover - only called on failure
        raise AssertionError("wakeword model should not initialize when AUDIO_ENABLED=False")

    monkeypatch.setattr(OpenWakeWordEngineAdapter, "_ensure_engine", fail_if_called)
    app = RuntimeApp(_runtime_config(AUDIO_ENABLED=False)).build()
    try:
        app.start()
    finally:
        app.close()

    assert app.registry.get("wakeword")._engine is None


def test_wakeword_adapter_rejects_audio_enabled_without_explicit_model():
    from sylphos.runtime.event_bus import EventBus

    adapter = OpenWakeWordEngineAdapter(EventBus(), enabled=True)

    try:
        adapter.start()
    except RuntimeError as exc:
        assert "requires an explicit wakeword model" in str(exc)
        assert "Refusing to load the openWakeWord default model" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected explicit wakeword model error")
