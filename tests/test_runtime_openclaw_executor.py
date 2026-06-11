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
