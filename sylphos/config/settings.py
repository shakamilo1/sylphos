from __future__ import annotations

"""Centralized Sylphos settings.

Runtime configuration is read from environment variables first.  The default
values below are intentionally safe for local development and do not contain
secrets.
"""

import os
from dataclasses import dataclass


OPENCLAW_BASE_URL = "http://127.0.0.1:18789"
OPENCLAW_TOKEN = ""
OPENCLAW_MODEL = "openclaw"
OPENCLAW_SESSION_KEY = "sylphos-main"
OPENCLAW_MESSAGE_CHANNEL = "sylphos-voice"
OPENCLAW_TIMEOUT_SECONDS = 120.0
OPENCLAW_MAX_SPOKEN_CHARS = 300


@dataclass(frozen=True)
class OpenClawSettings:
    """Configuration for the OpenClaw integration layer."""

    base_url: str = OPENCLAW_BASE_URL
    token: str = OPENCLAW_TOKEN
    model: str = OPENCLAW_MODEL
    session_key: str = OPENCLAW_SESSION_KEY
    message_channel: str = OPENCLAW_MESSAGE_CHANNEL
    timeout_seconds: float = OPENCLAW_TIMEOUT_SECONDS
    max_spoken_chars: int = OPENCLAW_MAX_SPOKEN_CHARS


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def get_openclaw_settings() -> OpenClawSettings:
    """Build OpenClaw settings from environment variables and safe defaults."""

    return OpenClawSettings(
        base_url=os.getenv("OPENCLAW_BASE_URL", OPENCLAW_BASE_URL),
        token=os.getenv("OPENCLAW_TOKEN", OPENCLAW_TOKEN),
        model=os.getenv("OPENCLAW_MODEL", OPENCLAW_MODEL),
        session_key=os.getenv("OPENCLAW_SESSION_KEY", OPENCLAW_SESSION_KEY),
        message_channel=os.getenv("OPENCLAW_MESSAGE_CHANNEL", OPENCLAW_MESSAGE_CHANNEL),
        timeout_seconds=_env_float("OPENCLAW_TIMEOUT_SECONDS", OPENCLAW_TIMEOUT_SECONDS),
        max_spoken_chars=_env_int("OPENCLAW_MAX_SPOKEN_CHARS", OPENCLAW_MAX_SPOKEN_CHARS),
    )
