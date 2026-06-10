from __future__ import annotations

"""Configuration helpers for the Sylphos OpenClaw bridge.

The defaults are safe for local development and contain no secrets. Values can
be overridden with environment variables or an untracked
``sylphos/config/local_config.py`` file that defines matching names.
"""

import importlib
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_PROVIDER = "openclaw"

OPENCLAW_MODE = "cli"  # cli / http / gateway / websocket
OPENCLAW_DRY_RUN = True

OPENCLAW_CLI_PATH = "openclaw"
OPENCLAW_WORKSPACE = None
OPENCLAW_TIMEOUT_SECONDS = 120

OPENCLAW_GATEWAY_URL = "ws://127.0.0.1:18789"
OPENCLAW_AUTH_TOKEN = None
OPENCLAW_CLIENT_ROLE = "operator"
OPENCLAW_SESSION_NAME = "sylphos"

OPENCLAW_LOG_RAW_OUTPUT = True
OPENCLAW_MAX_TTS_CHARS = 120
OPENCLAW_MAX_UI_CHARS = 4000
OPENCLAW_LOG_DIR = "logs"
OPENCLAW_SYLPHOS_LOG_PATH = "logs/sylphos.log"
OPENCLAW_AUDIT_LOG_PATH = "logs/audit.jsonl"


@dataclass(frozen=True, slots=True)
class OpenClawBridgeConfig:
    """Runtime configuration for :class:`SylphosOpenClawBridge`."""

    tool_provider: str = TOOL_PROVIDER
    mode: str = OPENCLAW_MODE
    dry_run: bool = OPENCLAW_DRY_RUN
    cli_path: str = OPENCLAW_CLI_PATH
    workspace: str | None = OPENCLAW_WORKSPACE
    timeout_seconds: float = OPENCLAW_TIMEOUT_SECONDS
    gateway_url: str = OPENCLAW_GATEWAY_URL
    auth_token: str | None = OPENCLAW_AUTH_TOKEN
    client_role: str = OPENCLAW_CLIENT_ROLE
    session_name: str = OPENCLAW_SESSION_NAME
    log_raw_output: bool = OPENCLAW_LOG_RAW_OUTPUT
    max_tts_chars: int = OPENCLAW_MAX_TTS_CHARS
    max_ui_chars: int = OPENCLAW_MAX_UI_CHARS
    log_dir: str = OPENCLAW_LOG_DIR
    sylphos_log_path: str = OPENCLAW_SYLPHOS_LOG_PATH
    audit_log_path: str = OPENCLAW_AUDIT_LOG_PATH


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _optional_text(name: str, default: str | None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    return value or None


def _load_local_overrides() -> dict[str, Any]:
    spec = importlib.util.find_spec("sylphos.config.local_config")
    if spec is None:
        return {}
    module = importlib.import_module("sylphos.config.local_config")
    names = {
        "TOOL_PROVIDER",
        "OPENCLAW_MODE",
        "OPENCLAW_DRY_RUN",
        "OPENCLAW_CLI_PATH",
        "OPENCLAW_WORKSPACE",
        "OPENCLAW_TIMEOUT_SECONDS",
        "OPENCLAW_GATEWAY_URL",
        "OPENCLAW_AUTH_TOKEN",
        "OPENCLAW_CLIENT_ROLE",
        "OPENCLAW_SESSION_NAME",
        "OPENCLAW_LOG_RAW_OUTPUT",
        "OPENCLAW_MAX_TTS_CHARS",
        "OPENCLAW_MAX_UI_CHARS",
        "OPENCLAW_LOG_DIR",
        "OPENCLAW_SYLPHOS_LOG_PATH",
        "OPENCLAW_AUDIT_LOG_PATH",
    }
    return {name: getattr(module, name) for name in names if hasattr(module, name)}


def load_openclaw_bridge_config() -> OpenClawBridgeConfig:
    """Load OpenClaw bridge settings from defaults, local config, and env vars."""

    values: dict[str, Any] = {
        "tool_provider": TOOL_PROVIDER,
        "mode": OPENCLAW_MODE,
        "dry_run": OPENCLAW_DRY_RUN,
        "cli_path": OPENCLAW_CLI_PATH,
        "workspace": OPENCLAW_WORKSPACE,
        "timeout_seconds": OPENCLAW_TIMEOUT_SECONDS,
        "gateway_url": OPENCLAW_GATEWAY_URL,
        "auth_token": OPENCLAW_AUTH_TOKEN,
        "client_role": OPENCLAW_CLIENT_ROLE,
        "session_name": OPENCLAW_SESSION_NAME,
        "log_raw_output": OPENCLAW_LOG_RAW_OUTPUT,
        "max_tts_chars": OPENCLAW_MAX_TTS_CHARS,
        "max_ui_chars": OPENCLAW_MAX_UI_CHARS,
        "log_dir": OPENCLAW_LOG_DIR,
        "sylphos_log_path": OPENCLAW_SYLPHOS_LOG_PATH,
        "audit_log_path": OPENCLAW_AUDIT_LOG_PATH,
    }

    for key, value in _load_local_overrides().items():
        field_name = key.removeprefix("OPENCLAW_").lower()
        if key == "TOOL_PROVIDER":
            field_name = "tool_provider"
        elif field_name == "cli_path":
            field_name = "cli_path"
        elif field_name == "dry_run":
            field_name = "dry_run"
        elif field_name == "log_raw_output":
            field_name = "log_raw_output"
        elif field_name == "max_tts_chars":
            field_name = "max_tts_chars"
        elif field_name == "max_ui_chars":
            field_name = "max_ui_chars"
        elif field_name == "log_dir":
            field_name = "log_dir"
        elif field_name == "sylphos_log_path":
            field_name = "sylphos_log_path"
        elif field_name == "audit_log_path":
            field_name = "audit_log_path"
        elif field_name == "auth_token":
            field_name = "auth_token"
        elif field_name == "timeout_seconds":
            field_name = "timeout_seconds"
        elif field_name == "gateway_url":
            field_name = "gateway_url"
        elif field_name == "client_role":
            field_name = "client_role"
        elif field_name == "session_name":
            field_name = "session_name"
        values[field_name] = value

    values.update(
        {
            "tool_provider": os.getenv("TOOL_PROVIDER", values["tool_provider"]),
            "mode": os.getenv("OPENCLAW_MODE", values["mode"]),
            "dry_run": _env_bool("OPENCLAW_DRY_RUN", bool(values["dry_run"])),
            "cli_path": os.getenv("OPENCLAW_CLI_PATH", str(values["cli_path"])),
            "workspace": _optional_text("OPENCLAW_WORKSPACE", values["workspace"]),
            "timeout_seconds": _env_float("OPENCLAW_TIMEOUT_SECONDS", float(values["timeout_seconds"])),
            "gateway_url": os.getenv("OPENCLAW_GATEWAY_URL", str(values["gateway_url"])),
            "auth_token": _optional_text("OPENCLAW_AUTH_TOKEN", values["auth_token"]),
            "client_role": os.getenv("OPENCLAW_CLIENT_ROLE", str(values["client_role"])),
            "session_name": os.getenv("OPENCLAW_SESSION_NAME", str(values["session_name"])),
            "log_raw_output": _env_bool("OPENCLAW_LOG_RAW_OUTPUT", bool(values["log_raw_output"])),
            "max_tts_chars": _env_int("OPENCLAW_MAX_TTS_CHARS", int(values["max_tts_chars"])),
            "max_ui_chars": _env_int("OPENCLAW_MAX_UI_CHARS", int(values["max_ui_chars"])),
            "log_dir": os.getenv("OPENCLAW_LOG_DIR", str(values["log_dir"])),
            "sylphos_log_path": os.getenv("OPENCLAW_SYLPHOS_LOG_PATH", str(values["sylphos_log_path"])),
            "audit_log_path": os.getenv("OPENCLAW_AUDIT_LOG_PATH", str(values["audit_log_path"])),
        }
    )

    Path(values["log_dir"]).mkdir(parents=True, exist_ok=True)
    return OpenClawBridgeConfig(**values)
