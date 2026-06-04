#!/usr/bin/env python
from __future__ import annotations

"""Manual OpenClaw health check.

Usage:
    python scripts/check_openclaw_health.py
"""

import sys
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sylphos.llm.openclaw_health import OpenClawHealthResult, check_openclaw_health

HealthChecker = Callable[[], OpenClawHealthResult]


def _short_text(text: str | None, *, limit: int = 500) -> str:
    if not text:
        return "<empty>"
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def format_health_result(result: OpenClawHealthResult) -> str:
    lines = [
        "OpenClaw health check",
        "",
        f"Status: {'PASS' if result.ok else 'FAIL'}",
    ]
    if not result.ok:
        lines.extend(
            [
                f"Reason: {result.status}",
                f"Message: {result.message}",
            ]
        )

    lines.extend(
        [
            f"Base URL: {result.base_url}",
            f"Model: {result.model}",
            f"Session: {result.session_key}",
            f"Channel: {result.message_channel}",
            f"Token present: {str(result.token_present).lower()}",
            f"Latency: {_format_latency(result.latency_ms)}",
        ]
    )

    if result.ok:
        lines.extend(
            [
                "",
                "Raw reply:",
                _short_text(result.raw_text),
                "",
                "Spoken reply:",
                _short_text(result.spoken_text),
            ]
        )
    elif result.suggestions:
        lines.extend(["", "Suggestions:"])
        lines.extend(f"- {suggestion}" for suggestion in result.suggestions)

    return "\n".join(lines)


def _format_latency(latency_ms: float | None) -> str:
    if latency_ms is None:
        return "n/a"
    return f"{latency_ms:.0f} ms"


def main(health_checker: HealthChecker = check_openclaw_health) -> int:
    result = health_checker()
    print(format_health_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
