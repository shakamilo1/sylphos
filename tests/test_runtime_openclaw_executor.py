from __future__ import annotations

from sylphos.config.loader import load_config
from sylphos.runtime.app import RuntimeApp
from sylphos.runtime.events import TextInputReceived, ToolExecutionRequested
from sylphos.runtime.state import RuntimeState


def test_text_input_routes_to_openclaw_when_configured(monkeypatch):
    monkeypatch.setenv("TOOL_EXECUTOR_PROVIDER", "openclaw")
    monkeypatch.setenv("OPENCLAW_DRY_RUN", "true")
    app = RuntimeApp(load_config()).build()
    completed = []
    app.event_bus.subscribe("tool.execution.completed", completed.append)
    try:
        app.start()
        app.event_bus.publish(TextInputReceived("打开浏览器", source="test"))
    finally:
        app.close()

    assert completed
    assert completed[-1].tool_name == "openclaw"
    assert completed[-1].result["ok"] is True
    assert completed[-1].result["status"] == "dry_run"
    assert app.context.state == RuntimeState.WAKEWORD_LISTENING


def test_openclaw_failure_publishes_failed_and_recovers(monkeypatch):
    monkeypatch.setenv("OPENCLAW_DRY_RUN", "false")
    monkeypatch.setenv("OPENCLAW_CLI_PATH", "definitely_missing_openclaw")
    app = RuntimeApp(load_config()).build()
    failed = []
    errors = []
    app.event_bus.subscribe("tool.execution.failed", failed.append)
    app.event_bus.subscribe("error.occurred", errors.append)
    try:
        app.start()
        app.event_bus.publish(ToolExecutionRequested("openclaw", {"command": "打开浏览器"}, source="test"))
    finally:
        app.close()

    assert failed
    assert failed[-1].tool_name == "openclaw"
    assert "command not found" in failed[-1].error
    assert failed[-1].result["ok"] is False
    assert errors
    assert app.context.state == RuntimeState.WAKEWORD_LISTENING


def test_openclaw_bridge_config_reuses_runtime_loader(monkeypatch, tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "local_config.py").write_text(
        'OPENCLAW_DRY_RUN = False\n'
        'TOOL_EXECUTOR_PROVIDER = "openclaw"\n'
        'OPENCLAW_MODE = "cli"\n'
        'OPENCLAW_CLI_PATH = "openclaw-from-local"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    from sylphos.config.loader import load_config
    from sylphos.executor.openclaw_config import load_openclaw_bridge_config

    runtime_config = load_config()
    bridge_config = load_openclaw_bridge_config()

    assert runtime_config.OPENCLAW_DRY_RUN is False
    assert bridge_config.dry_run is False
    assert bridge_config.mode == "cli"
    assert bridge_config.cli_path == "openclaw-from-local"


def test_openclaw_executor_false_dry_run_calls_cli_instead_of_dry_run(monkeypatch):
    import subprocess
    from types import SimpleNamespace

    from sylphos.executor.openclaw_config import OpenClawBridgeConfig
    from sylphos.executor.openclaw_executor import OpenClawExecutor
    from sylphos.runtime.context import RuntimeContext

    run_calls = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"success","message":"OpenClaw executed"}',
            stderr="",
        )

    monkeypatch.setattr("shutil.which", lambda command: "/usr/bin/openclaw")
    monkeypatch.setattr(subprocess, "run", fake_run)
    config = OpenClawBridgeConfig(
        mode="cli",
        dry_run=False,
        cli_path="openclaw",
        timeout_seconds=12,
        log_dir="logs",
        sylphos_log_path="logs/sylphos-test.log",
        audit_log_path="logs/audit-test.jsonl",
    )
    executor = OpenClawExecutor(config=config)

    result = executor.execute(
        ToolExecutionRequested("openclaw", {"command": "打开浏览器"}, source="test"),
        RuntimeContext(),
    )

    assert run_calls
    assert result["status"] != "dry_run"
    assert result["dry_run"] is False
    assert not any(action.get("dry_run") is True for action in result.get("actions", []))


def test_openclaw_extractor_speaks_plain_string():
    from sylphos.executor.openclaw_bridge import extract_speak_text_from_openclaw_response

    assert extract_speak_text_from_openclaw_response("真实回复") == "真实回复"


def test_openclaw_extractor_speaks_assistant_text():
    from sylphos.executor.openclaw_bridge import extract_speak_text_from_openclaw_response

    assert extract_speak_text_from_openclaw_response({"assistant_text": "助手最终回复"}) == "助手最终回复"


def test_openclaw_extractor_speaks_openai_compatible_content():
    from sylphos.executor.openclaw_bridge import extract_speak_text_from_openclaw_response

    response = {"choices": [{"message": {"content": "OpenAI 格式回复"}}]}
    assert extract_speak_text_from_openclaw_response(response) == "OpenAI 格式回复"


def test_openclaw_extractor_falls_back_only_for_status_only():
    from sylphos.executor.openclaw_bridge import extract_speak_text_from_openclaw_response

    assert extract_speak_text_from_openclaw_response({"ok": True, "status": "success"}) == "任务完成"


def test_openclaw_extractor_speaks_short_error():
    from sylphos.executor.openclaw_bridge import extract_speak_text_from_openclaw_response

    assert extract_speak_text_from_openclaw_response({"ok": False, "status": "failed", "error": "网关不可用"}) == "OpenClaw 执行失败：网关不可用"


def test_runtime_tts_receives_speak_text_not_fixed_status(monkeypatch):
    from types import SimpleNamespace

    from sylphos.runtime.app import RuntimeApp
    from sylphos.runtime.events import TextInputReceived

    spoken = []

    class FakeTTS:
        def speak(self, text):
            spoken.append(text)

    class FakeExecutor:
        def execute(self, request, context):
            return {
                "ok": True,
                "status": "success",
                "raw_response": {"assistant_text": "这是 OpenClaw 的真实回复"},
                "assistant_text": "这是 OpenClaw 的真实回复",
                "execution_status": "success",
                "speak_text": "这是 OpenClaw 的真实回复",
                "display_text": "这是 OpenClaw 的真实回复",
                "error_message": None,
            }

    config = SimpleNamespace(
        AUDIO_ENABLED=False,
        INPUT_RATE=44100,
        AUDIO_SAMPLE_RATE=44100,
        CHANNELS=1,
        AUDIO_CHANNELS=1,
        BLOCKSIZE=4410,
        AUDIO_BLOCKSIZE=4410,
        DTYPE="float32",
        STT_PROVIDER="dummy",
        DUMMY_STT_TEXT="请回复真实内容",
        TTS_PROVIDER="dummy",
        TOOL_EXECUTOR_PROVIDER="openclaw",
        OPENCLAW_DRY_RUN=True,
        ASR_POST_PROCESSORS=[],
    )
    app = RuntimeApp(config).build()
    app.registry.register("tts", SimpleNamespace(start=lambda: app.event_bus.subscribe("tts.requested", lambda e: FakeTTS().speak(e.text)), close=lambda: None))
    app.registry.register_executor("openclaw", FakeExecutor())

    try:
        app.start()
        app.event_bus.publish(TextInputReceived("请回复真实内容", source="test"))
    finally:
        app.close()

    assert "这是 OpenClaw 的真实回复" in spoken
    assert "任务完成" not in spoken


def test_runtime_tts_does_not_truncate_long_speak_text_by_default(monkeypatch):
    from types import SimpleNamespace

    from sylphos.runtime.app import RuntimeApp
    from sylphos.runtime.events import TextInputReceived

    long_text = "OpenClaw 返回的长回复。" * 20
    spoken = []

    class FakeExecutor:
        def execute(self, request, context):
            return {
                "ok": True,
                "status": "success",
                "raw_response": {"assistant_text": long_text},
                "assistant_text": long_text,
                "execution_status": "success",
                "speak_text": long_text,
                "display_text": long_text,
                "error_message": None,
            }

    config = SimpleNamespace(
        AUDIO_ENABLED=False,
        INPUT_RATE=44100,
        AUDIO_SAMPLE_RATE=44100,
        CHANNELS=1,
        AUDIO_CHANNELS=1,
        BLOCKSIZE=4410,
        AUDIO_BLOCKSIZE=4410,
        DTYPE="float32",
        STT_PROVIDER="dummy",
        DUMMY_STT_TEXT="请回复长文本",
        TTS_PROVIDER="dummy",
        TTS_MAX_SPEAK_CHARS=None,
        TOOL_EXECUTOR_PROVIDER="openclaw",
        OPENCLAW_DRY_RUN=True,
        ASR_POST_PROCESSORS=[],
    )
    app = RuntimeApp(config).build()
    app.registry.register(
        "tts",
        SimpleNamespace(
            start=lambda: app.event_bus.subscribe("tts.requested", lambda event: spoken.append(event.text)),
            close=lambda: None,
        ),
    )
    app.registry.register_executor("openclaw", FakeExecutor())

    try:
        app.start()
        app.event_bus.publish(TextInputReceived("请回复长文本", source="test"))
    finally:
        app.close()

    assert len(long_text) > 120
    assert long_text in spoken
    assert all(text == long_text for text in spoken if text.startswith("OpenClaw 返回的长回复。"))
