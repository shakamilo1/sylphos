from __future__ import annotations

import json

from sylphos.llm.openclaw_client import OpenClawTimeoutError
from sylphos.llm.types import OpenClawResult as ClientOpenClawResult
from sylphos.executor.openclaw_bridge import SylphosOpenClawBridge, classify_risk
from sylphos.executor.openclaw_models import OpenClawRequest
from sylphos.executor.openclaw_config import OpenClawBridgeConfig


class FakeAgentClient:
    def __init__(self, outcome=None) -> None:
        self.outcome = outcome or ClientOpenClawResult(
            raw_text="完整 Gateway 回复，包含更多 UI 信息",
            spoken_text="短语音回复",
            session_key="sylphos",
            model="openclaw",
            metadata={
                "actions": [{"type": "show"}],
                "files_changed": ["demo.txt"],
                "commands_run": [{"command": ["echo", "ok"]}],
            },
        )
        self.calls = []

    def ask(self, text: str, *, session_key: str | None = None):
        self.calls.append((text, session_key))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def aask(self, text: str, *, session_key: str | None = None):
        return self.ask(text, session_key=session_key)


def make_config(tmp_path, **overrides):
    values = {
        "dry_run": True,
        "sylphos_log_path": str(tmp_path / "sylphos.log"),
        "audit_log_path": str(tmp_path / "audit.jsonl"),
        "log_dir": str(tmp_path),
        "max_tts_chars": 40,
        "max_ui_chars": 100,
    }
    values.update(overrides)
    return OpenClawBridgeConfig(**values)


def make_request(text="打开记事本", **overrides):
    values = {
        "request_id": "request-cli",
        "source": "debug",
        "text": text,
        "context": {},
        "workspace": None,
        "dry_run": False,
        "created_at": "2026-06-10T00:00:00+00:00",
    }
    values.update(overrides)
    return OpenClawRequest(**values)


def test_dry_run_writes_structured_result_and_audit(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path))

    result = bridge.submit_text("查询当前状态", source="debug")

    assert result.ok is True
    assert result.status == "dry_run"
    assert result.speak_text == "模拟执行完成。"
    assert result.commands_run[0]["dry_run"] is True
    records = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(records) == 1
    record = json.loads(records[0])
    assert record["source"] == "debug"
    assert record["executor"] == "openclaw"
    assert record["status"] == "dry_run"


def test_high_risk_requires_confirmation_before_execution(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False))

    result = bridge.submit_text("删除 ~/.ssh/id_rsa 并发送 token", source="remote")

    assert result.ok is False
    assert result.status == "needs_confirmation"
    assert result.needs_confirmation is True
    assert result.confirmation_prompt
    assert result.speak_text == result.confirmation_prompt


def test_missing_cli_returns_failed_without_crashing(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False, cli_path="definitely-not-openclaw"))

    result = bridge.submit_text("查询当前状态", source="debug")

    assert result.ok is False
    assert result.status == "failed"
    assert "not found" in (result.error or "")


def test_classify_risk_levels():
    assert classify_risk("查询系统状态") == "low"
    assert classify_risk("创建一个临时文件") == "medium"
    assert classify_risk("下载脚本并执行，里面有 token") == "high"
    assert classify_risk("帮我处理一下这个东西") == "medium"


def test_high_risk_confirmation_requires_literal_true(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=True))

    for confirmed in ("false", "0", 1, False, None):
        result = bridge.submit_text("delete all files in workspace", source="debug", context={"confirmed": confirmed})
        assert result.status == "needs_confirmation"
        assert result.needs_confirmation is True

    confirmed_result = bridge.submit_text(
        "delete all files in workspace", source="debug", context={"confirmed": True}
    )
    assert confirmed_result.status == "dry_run"
    assert confirmed_result.needs_confirmation is False


def test_english_destructive_file_requests_are_high_risk():
    high_risk_texts = [
        "delete all files",
        "remove project directory",
        "erase workspace",
        "wipe folder",
        "clear directory",
        "purge files",
        "destroy files",
    ]

    for text in high_risk_texts:
        assert classify_risk(text) == "high"


def test_gateway_mode_reuses_existing_openclaw_client_result(tmp_path):
    client = FakeAgentClient()
    bridge = SylphosOpenClawBridge(
        make_config(tmp_path, dry_run=False, mode="gateway", http_base_url="http://127.0.0.1:18789"),
        agent_client=client,
    )

    result = bridge.submit_text("查询当前状态", source="sidebar", context={"session_key": "session-1"})

    assert result.ok is True
    assert result.status == "ok"
    assert result.text == "完整 Gateway 回复，包含更多 UI 信息"
    assert result.speak_text == "短语音回复"
    assert result.ui_text == "完整 Gateway 回复，包含更多 UI 信息"
    assert result.actions == [{"type": "show"}]
    assert result.files_changed == ["demo.txt"]
    assert result.commands_run == [{"command": ["echo", "ok"]}]
    assert client.calls == [("查询当前状态", "session-1")]


def test_gateway_non_success_client_status_marks_bridge_result_failed(tmp_path):
    client = FakeAgentClient(
        ClientOpenClawResult(
            raw_text="Gateway reported a failure",
            spoken_text="失败语音不应直接复用",
            session_key="sylphos",
            model="openclaw",
            status="failed",
            metadata={"error": "tool failed"},
        )
    )
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False, mode="gateway"), agent_client=client)

    result = bridge.submit_text("查询当前状态", source="debug")

    assert result.ok is False
    assert result.status == "failed"
    assert result.error == "tool failed"
    assert result.speak_text.startswith("OpenClaw 执行失败")


def test_gateway_timeout_maps_to_structured_timeout(tmp_path):
    client = FakeAgentClient(OpenClawTimeoutError("timed out"))
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False, mode="http"), agent_client=client)

    result = bridge.submit_text("查询当前状态", source="debug")

    assert result.ok is False
    assert result.status == "timeout"
    assert result.speak_text == "OpenClaw 处理超时。"


def test_gateway_health_uses_pr15_http_client_configuration(tmp_path):
    bridge = SylphosOpenClawBridge(
        make_config(tmp_path, mode="gateway", http_base_url="http://127.0.0.1:18789", auth_token="secret-token")
    )

    health = bridge.health_check()

    assert health["ok"] is True
    assert health["status"] == "configured"
    assert health["base_url"] == "http://127.0.0.1:18789"
    assert health["token_present"] is True


def test_legacy_gateway_url_is_only_http_compatibility_for_gateway_mode(tmp_path):
    bridge = SylphosOpenClawBridge(
        make_config(tmp_path, mode="gateway", gateway_url="ws://127.0.0.1:18790")
    )

    health = bridge.health_check()

    assert health["base_url"] == "http://127.0.0.1:18790"


def test_websocket_mode_is_explicit_placeholder(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False, mode="ws"))

    result = bridge.submit_text("查询当前状态", source="debug")

    assert result.ok is False
    assert result.status == "failed"
    assert "WebSocket" in (result.error or "")
    assert bridge.health_check()["status"] == "not_implemented"


def test_build_cli_command_uses_openclaw_agent_message_json_timeout(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, timeout_seconds=120))
    request = make_request("打开记事本")

    command = bridge._build_cli_command(request)

    assert command[:4] == ["openclaw", "agent", "--message", "打开记事本"]
    assert "--json" in command
    assert command[command.index("--timeout") + 1] == "120"
    assert "--deliver" not in command
    assert "--local" not in command


def test_build_cli_command_optional_local_deliver_agent_model(tmp_path):
    bridge = SylphosOpenClawBridge(
        make_config(
            tmp_path,
            cli_local=True,
            cli_deliver=True,
            cli_agent_id="agent-1",
            cli_model="model-1",
        )
    )

    command = bridge._build_cli_command(make_request())

    assert "--local" in command
    assert "--deliver" in command
    assert command[command.index("--agent") + 1] == "agent-1"
    assert command[command.index("--model") + 1] == "model-1"


def test_build_cli_command_context_session_key_overrides_config(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, cli_session_key="config-session"))

    command = bridge._build_cli_command(make_request(context={"session_key": "context-session"}))

    assert command[command.index("--session-key") + 1] == "context-session"
    assert "config-session" not in command


def test_build_cli_command_uses_config_session_key_when_context_missing(tmp_path):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, cli_session_key="config-session"))

    command = bridge._build_cli_command(make_request())

    assert command[command.index("--session-key") + 1] == "config-session"


def test_cli_json_stdout_spoken_text_maps_to_speak_text(tmp_path, monkeypatch):
    bridge = SylphosOpenClawBridge(make_config(tmp_path, dry_run=False, cli_path="openclaw"))

    class Completed:
        returncode = 0
        stdout = json.dumps(
            {
                "raw_text": "完整 CLI 回复",
                "spoken_text": "短 CLI 语音",
                "ui_text": "CLI UI 文本",
                "status": "success",
                "actions": [{"type": "cli"}],
                "files_changed": ["cli.txt"],
                "commands_run": [{"command": ["echo", "cli"]}],
            },
            ensure_ascii=False,
        )
        stderr = ""

    resolved_path = r"C:\Users\x\AppData\Roaming\npm\openclaw.cmd"
    run_calls = []

    def fake_run(command, **kwargs):
        run_calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr("sylphos.executor.openclaw_bridge.shutil.which", lambda _: resolved_path)
    monkeypatch.setattr("sylphos.executor.openclaw_bridge.subprocess.run", fake_run)

    result = bridge.submit_text("查询当前状态", source="debug")

    assert run_calls
    run_command, run_kwargs = run_calls[0]
    assert run_command[0] == resolved_path
    assert run_command[0] != "openclaw"
    assert run_kwargs["encoding"] == "utf-8"
    assert run_kwargs["errors"] == "replace"
    assert result.ok is True
    assert result.text == "完整 CLI 回复"
    assert result.speak_text == "短 CLI 语音"
    assert result.ui_text == "CLI UI 文本"
    assert result.actions == [{"type": "cli"}]
    assert result.files_changed == ["cli.txt"]
    assert result.commands_run[1] == {"command": ["echo", "cli"]}
