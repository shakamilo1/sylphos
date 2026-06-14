from __future__ import annotations

"""Structured request and result models for the Sylphos OpenClaw bridge."""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    """Return the current UTC time in an audit-friendly ISO-8601 format."""

    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class OpenClawRequest:
    """A source-agnostic text/task request sent from Sylphos to OpenClaw."""

    request_id: str
    source: str
    text: str
    context: dict[str, Any] = field(default_factory=dict)
    workspace: str | None = None
    dry_run: bool = True
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the request for logs, tests, and future event bus payloads."""

        return asdict(self)


@dataclass(slots=True)
class OpenClawBridgeResult:
    """Structured execution result returned by OpenClawBridge to downstream Sylphos modules."""

    request_id: str
    ok: bool
    status: str
    text: str | None = None
    speak_text: str | None = None
    ui_text: str | None = None
    raw_response: Any | None = None
    assistant_text: str | None = None
    execution_status: str | None = None
    display_text: str | None = None
    error_message: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    commands_run: list[dict[str, Any]] = field(default_factory=list)
    needs_confirmation: bool = False
    confirmation_prompt: str | None = None
    raw_stdout: str | None = None
    raw_stderr: str | None = None
    exit_code: int | None = None
    error: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for audit records or UI adapters."""

        return asdict(self)
