from __future__ import annotations

import pytest

from scripts.check_openclaw_health import format_health_result, main
from sylphos.config.settings import OpenClawSettings
from sylphos.llm.openclaw_client import (
    OpenClawAuthError,
    OpenClawConnectionError,
    OpenClawResponseError,
    OpenClawTimeoutError,
)
from sylphos.llm.openclaw_health import (
    HEALTH_CHECK_PROMPT,
    STATUS_API_NOT_ENABLED,
    STATUS_AUTH_ERROR,
    STATUS_CONNECTION_ERROR,
    STATUS_INVALID_CONFIG,
    STATUS_INVALID_RESPONSE,
    STATUS_OK,
    STATUS_TIMEOUT,
    STATUS_UNEXPECTED_ERROR,
    OpenClawHealthResult,
    check_openclaw_health,
)
from sylphos.llm.types import OpenClawResult


@pytest.fixture
def settings() -> OpenClawSettings:
    return OpenClawSettings(
        base_url="http://127.0.0.1:18789",
        token="secret-token",
        model="openclaw",
        session_key="sylphos-main",
        message_channel="sylphos-voice",
        timeout_seconds=3,
        max_spoken_chars=300,
    )


def with_settings(settings: OpenClawSettings, **overrides) -> OpenClawSettings:
    return OpenClawSettings(**{**settings.__dict__, **overrides})


class FakeClient:
    def __init__(self, outcome=None) -> None:
        self.outcome = outcome or OpenClawResult(
            raw_text="OK",
            spoken_text="OK",
            session_key="sylphos-main",
            model="openclaw",
            metadata={
                "finish_reason": "stop",
                "run_id": "run-health",
                "usage": {"total_tokens": 3},
                "raw_response": {"secret": "do-not-copy"},
            },
        )
        self.calls: list[tuple[str, str | None]] = []

    def ask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        self.calls.append((text, session_key))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def aask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        return self.ask(text, session_key=session_key)


def test_health_ok_returns_ok(settings):
    client = FakeClient()

    result = check_openclaw_health(client=client, settings=settings)

    assert result.ok is True
    assert result.status == STATUS_OK
    assert result.raw_text == "OK"
    assert result.spoken_text == "OK"
    assert result.token_present is True
    assert result.latency_ms is not None
    assert client.calls == [(HEALTH_CHECK_PROMPT, "sylphos-main")]
    assert result.metadata == {
        "finish_reason": "stop",
        "run_id": "run-health",
        "usage": {"total_tokens": 3},
    }
    assert "raw_response" not in result.metadata


def test_token_not_leaked_only_token_present(settings):
    result = check_openclaw_health(
        client=FakeClient(OpenClawConnectionError("failed with secret-token")),
        settings=settings,
    )
    rendered = format_health_result(result)

    assert result.token_present is True
    assert "secret-token" not in rendered
    assert "Token present: true" in rendered
    assert "<redacted>" in rendered


def test_timeout_seconds_invalid_config(settings):
    result = check_openclaw_health(client=FakeClient(), settings=with_settings(settings, timeout_seconds=0))

    assert result.ok is False
    assert result.status == STATUS_INVALID_CONFIG
    assert any("OPENCLAW_TIMEOUT_SECONDS" in suggestion for suggestion in result.suggestions)


def test_max_spoken_chars_invalid_config(settings):
    result = check_openclaw_health(client=FakeClient(), settings=with_settings(settings, max_spoken_chars=0))

    assert result.ok is False
    assert result.status == STATUS_INVALID_CONFIG
    assert any("OPENCLAW_MAX_SPOKEN_CHARS" in suggestion for suggestion in result.suggestions)


def test_empty_base_url_invalid_config(settings):
    result = check_openclaw_health(client=FakeClient(), settings=with_settings(settings, base_url=""))

    assert result.ok is False
    assert result.status == STATUS_INVALID_CONFIG
    assert any("OPENCLAW_BASE_URL" in suggestion for suggestion in result.suggestions)


@pytest.mark.parametrize(
    ("exc", "expected_status"),
    [
        (OpenClawConnectionError("gateway down"), STATUS_CONNECTION_ERROR),
        (OpenClawAuthError("bad token"), STATUS_AUTH_ERROR),
        (OpenClawTimeoutError("timed out"), STATUS_TIMEOUT),
        (OpenClawResponseError("HTTP 404: not found"), STATUS_API_NOT_ENABLED),
        (OpenClawResponseError("missing choices"), STATUS_INVALID_RESPONSE),
        (RuntimeError("boom"), STATUS_UNEXPECTED_ERROR),
    ],
)
def test_exception_status_mapping(settings, exc, expected_status):
    result = check_openclaw_health(client=FakeClient(exc), settings=settings)

    assert result.ok is False
    assert result.status == expected_status
    assert result.suggestions


def test_api_not_enabled_mentions_chat_completions(settings):
    result = check_openclaw_health(
        client=FakeClient(OpenClawResponseError("chat completions not enabled")),
        settings=settings,
    )

    assert result.status == STATUS_API_NOT_ENABLED
    assert any("chatCompletions.enabled" in suggestion for suggestion in result.suggestions)


def test_cli_success_returns_zero_and_prints_pass(capsys):
    result = OpenClawHealthResult(
        ok=True,
        status=STATUS_OK,
        message="ok",
        base_url="http://127.0.0.1:18789",
        model="openclaw",
        session_key="sylphos-main",
        message_channel="sylphos-voice",
        token_present=False,
        latency_ms=532,
        raw_text="OK",
        spoken_text="OK",
    )

    exit_code = main(lambda: result)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Status: PASS" in out
    assert "Token present: false" in out
    assert "Raw reply:" in out
    assert "Spoken reply:" in out


def test_cli_failure_returns_one_and_prints_suggestions(capsys):
    result = OpenClawHealthResult(
        ok=False,
        status=STATUS_CONNECTION_ERROR,
        message="OpenClaw Gateway is unreachable.",
        base_url="http://127.0.0.1:18789",
        model="openclaw",
        session_key="sylphos-main",
        message_channel="sylphos-voice",
        token_present=False,
        latency_ms=None,
        suggestions=["Start OpenClaw Gateway.", "Check OPENCLAW_BASE_URL."],
    )

    exit_code = main(lambda: result)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "Status: FAIL" in out
    assert "Reason: connection_error" in out
    assert "Suggestions:" in out
    assert "- Start OpenClaw Gateway." in out


def test_cli_output_does_not_contain_real_token(capsys):
    result = OpenClawHealthResult(
        ok=False,
        status=STATUS_AUTH_ERROR,
        message="bad credentials",
        base_url="http://127.0.0.1:18789",
        model="openclaw",
        session_key="sylphos-main",
        message_channel="sylphos-voice",
        token_present=True,
        suggestions=["确认 OPENCLAW_TOKEN 是否正确。"],
    )

    exit_code = main(lambda: result)

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "secret-token" not in out
    assert "Token present: true" in out
