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


def test_runtime_app_passes_wake_score_display_config():
    app = RuntimeApp(
        _runtime_config(
            CONSOLE_WAKE_SCORE_DISPLAY="log",
            WAKEWORD_SCORE_LOG_INTERVAL_SECONDS=2.5,
        )
    ).build()

    wakeword = app.registry.get("wakeword")

    assert wakeword.console_wake_score_display == "log"
    assert wakeword.wakeword_score_log_interval_seconds == 2.5


def test_console_feedback_saves_wake_score_and_detected_output(capsys):
    from sylphos.frontend.console_feedback import ConsoleFeedback
    from sylphos.runtime.event_bus import EventBus
    from sylphos.runtime.events import WakeWordDetected, WakeWordScoreUpdated

    bus = EventBus()
    feedback = ConsoleFeedback(bus)
    feedback.start()
    try:
        bus.publish(WakeWordScoreUpdated(name="hey_jarvis_v0.1", score=0.123))
        score_out = capsys.readouterr().out
        bus.publish(WakeWordDetected(name="hey_jarvis_v0.1", score=0.987))
        detected_out = capsys.readouterr().out
    finally:
        feedback.close()

    assert "[wake max]" not in score_out
    assert feedback.latest_wake_score.name == "hey_jarvis_v0.1"
    assert feedback.latest_wake_score.score == 0.123
    assert "wake detected" in detected_out
    assert "0.987" in detected_out


def test_openwakeword_score_updates_do_not_info_log_by_default(caplog):
    import logging
    import numpy as np

    from voice.wakeword.openwakeword_engine import OpenWakeWordEngine

    class FakeModel:
        def predict(self, audio):
            return {"hey_jarvis_v0.1": 0.0}

    seen = []
    engine = OpenWakeWordEngine.__new__(OpenWakeWordEngine)
    engine.input_rate = 44100
    engine.target_rate = 16000
    engine.threshold = 0.5
    engine.cooldown_seconds = 2.0
    engine.on_detect = None
    engine.on_score = lambda name, score: seen.append((name, score))
    engine.score_log_interval_seconds = 0.0
    engine.log_scores_to_info = False
    engine._logger = logging.getLogger("OpenWakeWordEngine")
    engine._last_trigger_time = 0.0
    engine._last_print_time = 0.0
    engine._enabled = True
    engine._resample = lambda audio: audio.astype(np.float32)
    engine._model = FakeModel()

    with caplog.at_level(logging.INFO):
        engine.consume(np.zeros(16, dtype=np.float32))

    assert seen == [("hey_jarvis_v0.1", 0.0)]
    assert "[wake max]" not in caplog.text


def test_openwakeword_score_log_mode_restores_info_log(caplog):
    import logging
    import numpy as np

    from voice.wakeword.openwakeword_engine import OpenWakeWordEngine

    class FakeModel:
        def predict(self, audio):
            return {"hey_jarvis_v0.1": 0.0}

    engine = OpenWakeWordEngine.__new__(OpenWakeWordEngine)
    engine.input_rate = 44100
    engine.target_rate = 16000
    engine.threshold = 0.5
    engine.cooldown_seconds = 2.0
    engine.on_detect = None
    engine.on_score = None
    engine.score_log_interval_seconds = 0.0
    engine.log_scores_to_info = True
    engine._logger = logging.getLogger("OpenWakeWordEngine")
    engine._last_trigger_time = 0.0
    engine._last_print_time = 0.0
    engine._enabled = True
    engine._resample = lambda audio: audio.astype(np.float32)
    engine._model = FakeModel()

    with caplog.at_level(logging.INFO):
        engine.consume(np.zeros(16, dtype=np.float32))

    assert "[wake max] hey_jarvis_v0.1: 0.000" in caplog.text
