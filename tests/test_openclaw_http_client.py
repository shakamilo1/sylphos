from __future__ import annotations

import json
import socket
from urllib import error

import pytest

from sylphos.config.settings import OpenClawSettings
from sylphos.llm.openclaw_client import (
    OpenClawAuthError,
    OpenClawConnectionError,
    OpenClawResponseError,
    OpenClawTimeoutError,
    SpeechReplyAdapter,
)
from sylphos.llm.openclaw_http_client import OpenClawHTTPClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


@pytest.fixture
def settings() -> OpenClawSettings:
    return OpenClawSettings(
        base_url="http://127.0.0.1:18789",
        token="",
        model="openclaw",
        session_key="sylphos-main",
        message_channel="sylphos-voice",
        timeout_seconds=3,
        max_spoken_chars=300,
    )


def install_urlopen(monkeypatch, payload: dict, calls: list) -> None:
    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse(payload)

    monkeypatch.setattr("sylphos.llm.openclaw_http_client.request.urlopen", fake_urlopen)


def test_normal_return_content(settings, monkeypatch):
    calls = []
    install_urlopen(
        monkeypatch,
        {
            "id": "run-1",
            "model": "openclaw",
            "choices": [{"message": {"content": "已经打开 Sylphos 项目。"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 12},
        },
        calls,
    )

    result = OpenClawHTTPClient(settings=settings).ask("打开 Sylphos 项目")

    assert result.raw_text == "已经打开 Sylphos 项目。"
    assert result.spoken_text == "已经打开 Sylphos 项目。"
    assert result.session_key == "sylphos-main"
    assert result.model == "openclaw"
    assert result.metadata["finish_reason"] == "stop"
    assert result.metadata["usage"] == {"total_tokens": 12}
    assert result.metadata["raw_response"]["id"] == "run-1"
    assert calls[0][1] == 3


def test_empty_token_does_not_send_authorization(settings, monkeypatch):
    calls = []
    install_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]}, calls)

    OpenClawHTTPClient(settings=settings).ask("hello")

    req, _ = calls[0]
    assert req.get_header("Authorization") is None


def test_non_empty_token_sends_authorization(settings, monkeypatch):
    calls = []
    install_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]}, calls)
    client = OpenClawHTTPClient(settings=OpenClawSettings(**{**settings.__dict__, "token": "secret-token"}))

    client.ask("hello")

    req, _ = calls[0]
    assert req.get_header("Authorization") == "Bearer secret-token"


def test_default_session_key(settings, monkeypatch):
    calls = []
    install_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]}, calls)

    OpenClawHTTPClient(settings=settings).ask("hello")

    req, _ = calls[0]
    body = json.loads(req.data.decode("utf-8"))
    assert req.headers["X-openclaw-session-key"] == "sylphos-main"
    assert body["user"] == "sylphos-main"


def test_ask_overrides_session_key(settings, monkeypatch):
    calls = []
    install_urlopen(monkeypatch, {"choices": [{"message": {"content": "ok"}}]}, calls)

    result = OpenClawHTTPClient(settings=settings).ask("hello", session_key="custom-session")

    req, _ = calls[0]
    body = json.loads(req.data.decode("utf-8"))
    assert result.session_key == "custom-session"
    assert req.headers["X-openclaw-session-key"] == "custom-session"
    assert body["user"] == "custom-session"


def test_http_401_maps_to_auth_error(settings, monkeypatch):
    def fake_urlopen(req, timeout):
        raise error.HTTPError(req.full_url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr("sylphos.llm.openclaw_http_client.request.urlopen", fake_urlopen)

    with pytest.raises(OpenClawAuthError):
        OpenClawHTTPClient(settings=settings).ask("hello")


def test_connection_failure_maps_to_connection_error(settings, monkeypatch):
    def fake_urlopen(req, timeout):
        raise error.URLError("connection refused")

    monkeypatch.setattr("sylphos.llm.openclaw_http_client.request.urlopen", fake_urlopen)

    with pytest.raises(OpenClawConnectionError):
        OpenClawHTTPClient(settings=settings).ask("hello")


def test_timeout_maps_to_timeout_error(settings, monkeypatch):
    def fake_urlopen(req, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr("sylphos.llm.openclaw_http_client.request.urlopen", fake_urlopen)

    with pytest.raises(OpenClawTimeoutError):
        OpenClawHTTPClient(settings=settings).ask("hello")


def test_missing_choices_maps_to_response_error(settings, monkeypatch):
    calls = []
    install_urlopen(monkeypatch, {"id": "bad"}, calls)

    with pytest.raises(OpenClawResponseError):
        OpenClawHTTPClient(settings=settings).ask("hello")


def test_spoken_text_cleans_markdown():
    adapter = SpeechReplyAdapter(max_spoken_chars=300)
    raw = "# 标题\n```python\nprint('x')\n```\n- **你好**，[Sylphos](https://example.test) Greek: αβγ"

    spoken = adapter.adapt(raw)

    assert "```" not in spoken
    assert "**" not in spoken
    assert "[" not in spoken
    assert "标题" in spoken
    assert "Sylphos" in spoken
    assert "αβγ" in spoken


def test_spoken_text_truncates_long_text():
    adapter = SpeechReplyAdapter(max_spoken_chars=20)

    spoken = adapter.adapt("一" * 50)

    assert len(spoken) <= 20
    assert spoken.endswith("后面的内容我已经保留在日志里。")


def test_raw_text_preserves_full_content(settings, monkeypatch):
    raw = "**" + "一" * 500 + "**"
    short_settings = OpenClawSettings(**{**settings.__dict__, "max_spoken_chars": 40})
    calls = []
    install_urlopen(monkeypatch, {"choices": [{"message": {"content": raw}}]}, calls)

    result = OpenClawHTTPClient(settings=short_settings).ask("long")

    assert result.raw_text == raw
    assert len(result.spoken_text) <= 40
    assert result.spoken_text != result.raw_text
