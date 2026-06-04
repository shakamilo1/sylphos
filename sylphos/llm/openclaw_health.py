from __future__ import annotations

"""OpenClaw Gateway health checks for Sylphos.

The health check sends one low-risk prompt through the existing agent client and
turns common failures into stable status strings suitable for CLI output or a
future UI. It deliberately does not store tokens or full raw Gateway responses.
"""

import time
from dataclasses import dataclass, field
from typing import Any

from sylphos.config.settings import OpenClawSettings, get_openclaw_settings
from sylphos.llm.base import BaseAgentClient
from sylphos.llm.openclaw_client import (
    OpenClawAuthError,
    OpenClawConnectionError,
    OpenClawResponseError,
    OpenClawTimeoutError,
    create_openclaw_client,
)

HEALTH_CHECK_PROMPT = "请只回复 OK，不要执行任何工具。"

STATUS_OK = "ok"
STATUS_INVALID_CONFIG = "invalid_config"
STATUS_CONNECTION_ERROR = "connection_error"
STATUS_AUTH_ERROR = "auth_error"
STATUS_API_NOT_ENABLED = "api_not_enabled"
STATUS_TIMEOUT = "timeout"
STATUS_INVALID_RESPONSE = "invalid_response"
STATUS_UNEXPECTED_ERROR = "unexpected_error"


@dataclass
class OpenClawHealthResult:
    """Diagnostic result for the OpenClaw integration.

    ``token_present`` is intentionally only a boolean. ``metadata`` should only
    contain sanitized summary fields and must not include full raw Gateway
    responses by default.
    """

    ok: bool
    status: str
    message: str
    base_url: str
    model: str
    session_key: str
    message_channel: str
    token_present: bool
    latency_ms: float | None = None
    raw_text: str | None = None
    spoken_text: str | None = None
    error_type: str | None = None
    suggestions: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def check_openclaw_health(
    *,
    client: BaseAgentClient | None = None,
    settings: OpenClawSettings | None = None,
) -> OpenClawHealthResult:
    """Check whether Sylphos can reach OpenClaw through the configured client.

    This function catches integration/runtime failures and returns a structured
    result instead of raising, so CLI callers can produce clear PASS/FAIL output.
    """

    active_settings = settings or getattr(client, "settings", None) or get_openclaw_settings()
    invalid_suggestions = _validate_settings(active_settings)
    if invalid_suggestions:
        return _result(
            settings=active_settings,
            ok=False,
            status=STATUS_INVALID_CONFIG,
            message="OpenClaw configuration is invalid.",
            error_type=STATUS_INVALID_CONFIG,
            suggestions=invalid_suggestions,
        )

    active_client = client or create_openclaw_client(active_settings)
    started = time.perf_counter()
    try:
        result = active_client.ask(HEALTH_CHECK_PROMPT, session_key=active_settings.session_key)
    except OpenClawAuthError as exc:
        return _failure(
            settings=active_settings,
            status=STATUS_AUTH_ERROR,
            exc=exc,
            started=started,
            suggestions=[
                "确认 OPENCLAW_TOKEN 是否正确。",
                "如果 Gateway 未启用 token，清空 OPENCLAW_TOKEN。",
            ],
        )
    except OpenClawTimeoutError as exc:
        return _failure(
            settings=active_settings,
            status=STATUS_TIMEOUT,
            exc=exc,
            started=started,
            suggestions=[
                "增大 OPENCLAW_TIMEOUT_SECONDS。",
                "检查 Gateway 或 Agent 是否卡住。",
            ],
        )
    except OpenClawConnectionError as exc:
        return _failure(
            settings=active_settings,
            status=STATUS_CONNECTION_ERROR,
            exc=exc,
            started=started,
            suggestions=[
                "确认 OpenClaw Gateway 是否已经启动。",
                "确认 OPENCLAW_BASE_URL 是否正确。",
                "默认本机地址是 http://127.0.0.1:18789。",
            ],
        )
    except OpenClawResponseError as exc:
        response_status = _response_error_status(str(exc))
        suggestions = [
            "检查 OpenClaw Gateway 版本和 API 返回格式。",
            "使用 scripts/test_openclaw_text.py 做完整文本往返测试。",
        ]
        if response_status == STATUS_API_NOT_ENABLED:
            suggestions = [
                "确认 OpenClaw Gateway 是否启用了 OpenAI-compatible /v1/chat/completions。",
                "检查 gateway.http.endpoints.chatCompletions.enabled 是否为 true。",
            ]
        return _failure(
            settings=active_settings,
            status=response_status,
            exc=exc,
            started=started,
            suggestions=suggestions,
        )
    except Exception as exc:  # pragma: no cover - exercised with explicit test fake
        return _failure(
            settings=active_settings,
            status=STATUS_UNEXPECTED_ERROR,
            exc=exc,
            started=started,
            suggestions=[
                "查看 Sylphos/OpenClaw 日志中的异常栈。",
                "确认当前 OpenClaw client 实现与 Sylphos 版本匹配。",
            ],
        )

    latency_ms = _elapsed_ms(started)
    return _result(
        settings=active_settings,
        ok=True,
        status=STATUS_OK,
        message="OpenClaw Gateway returned a valid text response.",
        latency_ms=latency_ms,
        raw_text=result.raw_text,
        spoken_text=result.spoken_text,
        metadata={
            "finish_reason": result.metadata.get("finish_reason"),
            "run_id": result.metadata.get("run_id"),
            "usage": result.metadata.get("usage"),
        },
    )


def _validate_settings(settings: OpenClawSettings) -> list[str]:
    suggestions: list[str] = []
    if not settings.base_url.strip():
        suggestions.append("设置 OPENCLAW_BASE_URL，例如 http://127.0.0.1:18789。")
    if not settings.model.strip():
        suggestions.append("设置 OPENCLAW_MODEL，例如 openclaw。")
    if not settings.session_key.strip():
        suggestions.append("设置 OPENCLAW_SESSION_KEY，例如 sylphos-main。")
    if not settings.message_channel.strip():
        suggestions.append("设置 OPENCLAW_MESSAGE_CHANNEL，例如 sylphos-voice。")
    if settings.timeout_seconds <= 0:
        suggestions.append("OPENCLAW_TIMEOUT_SECONDS 必须大于 0。")
    if settings.max_spoken_chars <= 0:
        suggestions.append("OPENCLAW_MAX_SPOKEN_CHARS 必须大于 0。")
    return suggestions


def _redact_token(message: str, token: str) -> str:
    if token:
        return message.replace(token, "<redacted>")
    return message


def _response_error_status(message: str) -> str:
    lowered = message.lower()
    if "404" in lowered or "not found" in lowered or "not enabled" in lowered:
        return STATUS_API_NOT_ENABLED
    return STATUS_INVALID_RESPONSE


def _failure(
    *,
    settings: OpenClawSettings,
    status: str,
    exc: Exception,
    started: float,
    suggestions: list[str],
) -> OpenClawHealthResult:
    return _result(
        settings=settings,
        ok=False,
        status=status,
        message=_redact_token(str(exc), settings.token),
        latency_ms=_elapsed_ms(started),
        error_type=exc.__class__.__name__,
        suggestions=suggestions,
    )


def _result(
    *,
    settings: OpenClawSettings,
    ok: bool,
    status: str,
    message: str,
    latency_ms: float | None = None,
    raw_text: str | None = None,
    spoken_text: str | None = None,
    error_type: str | None = None,
    suggestions: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> OpenClawHealthResult:
    return OpenClawHealthResult(
        ok=ok,
        status=status,
        message=message,
        base_url=settings.base_url,
        model=settings.model,
        session_key=settings.session_key,
        message_channel=settings.message_channel,
        token_present=bool(settings.token),
        latency_ms=latency_ms,
        raw_text=raw_text,
        spoken_text=spoken_text,
        error_type=error_type,
        suggestions=suggestions or [],
        metadata=metadata or {},
    )


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
