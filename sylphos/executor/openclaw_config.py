from __future__ import annotations

"""Configuration helpers for the Sylphos OpenClaw bridge.

The defaults are safe for local development and contain no secrets. Values can
be overridden with environment variables or an untracked
project-root ``local_config.py`` file that defines matching names.
"""

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOOL_PROVIDER = "openclaw"

OPENCLAW_MODE = "cli"  # cli / http / gateway / websocket / ws
OPENCLAW_DRY_RUN = True

OPENCLAW_CLI_PATH = "openclaw"
# Runtime-friendly aliases. Prefer OPENCLAW_CLI_PATH / OPENCLAW_WORKSPACE /
# OPENCLAW_HTTP_BASE_URL / OPENCLAW_GATEWAY_WS_URL / OPENCLAW_AUTH_TOKEN in
# OpenClaw bridge code, but accept the shorter names requested by Runtime users.
OPENCLAW_CLI = OPENCLAW_CLI_PATH
OPENCLAW_CLI_AGENT_ID = None
OPENCLAW_CLI_MODEL = None
OPENCLAW_CLI_SESSION_KEY = None
OPENCLAW_CLI_LOCAL = False
OPENCLAW_CLI_DELIVER = False
OPENCLAW_CLI_JSON = True
OPENCLAW_WORKSPACE = None
OPENCLAW_WORKDIR = OPENCLAW_WORKSPACE
OPENCLAW_TIMEOUT_SECONDS = 120

OPENCLAW_HTTP_BASE_URL = "http://127.0.0.1:18789"
OPENCLAW_API_URL = OPENCLAW_HTTP_BASE_URL
OPENCLAW_GATEWAY_WS_URL = "ws://127.0.0.1:18789"
OPENCLAW_WS_URL = OPENCLAW_GATEWAY_WS_URL
# Deprecated compatibility alias for early PR #19 drafts. Prefer the two
# transport-specific settings above.
OPENCLAW_GATEWAY_URL = None
OPENCLAW_AUTH_TOKEN = None
OPENCLAW_TOKEN = OPENCLAW_AUTH_TOKEN
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
    cli_agent_id: str | None = OPENCLAW_CLI_AGENT_ID
    cli_model: str | None = OPENCLAW_CLI_MODEL
    cli_session_key: str | None = OPENCLAW_CLI_SESSION_KEY
    cli_local: bool = OPENCLAW_CLI_LOCAL
    cli_deliver: bool = OPENCLAW_CLI_DELIVER
    cli_json: bool = OPENCLAW_CLI_JSON
    workspace: str | None = OPENCLAW_WORKSPACE
    timeout_seconds: float = OPENCLAW_TIMEOUT_SECONDS
    http_base_url: str = OPENCLAW_HTTP_BASE_URL
    gateway_ws_url: str = OPENCLAW_GATEWAY_WS_URL
    gateway_url: str | None = OPENCLAW_GATEWAY_URL
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


def _gateway_url_to_http_base_url(gateway_url: str | None) -> str | None:
    if not gateway_url:
        return None
    if gateway_url.startswith("ws://"):
        return "http://" + gateway_url.removeprefix("ws://")
    if gateway_url.startswith("wss://"):
        return "https://" + gateway_url.removeprefix("wss://")
    return gateway_url


def _load_local_overrides() -> dict[str, Any]:
    module = None
    local_config_path = Path(__file__).resolve().parents[2] / "local_config.py"
    if local_config_path.is_file():
        spec = importlib.util.spec_from_file_location("sylphos_openclaw_local_config", local_config_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Failed to load local config file: {local_config_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    if module is None:
        return {}
    names = {
        "TOOL_PROVIDER",
        "OPENCLAW_MODE",
        "OPENCLAW_DRY_RUN",
        "OPENCLAW_CLI_PATH",
        "OPENCLAW_CLI",
        "OPENCLAW_CLI_AGENT_ID",
        "OPENCLAW_CLI_MODEL",
        "OPENCLAW_CLI_SESSION_KEY",
        "OPENCLAW_CLI_LOCAL",
        "OPENCLAW_CLI_DELIVER",
        "OPENCLAW_CLI_JSON",
        "OPENCLAW_WORKSPACE",
        "OPENCLAW_WORKDIR",
        "OPENCLAW_TIMEOUT_SECONDS",
        "OPENCLAW_HTTP_BASE_URL",
        "OPENCLAW_API_URL",
        "OPENCLAW_GATEWAY_WS_URL",
        "OPENCLAW_WS_URL",
        "OPENCLAW_GATEWAY_URL",
        "OPENCLAW_AUTH_TOKEN",
        "OPENCLAW_TOKEN",
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


_LOCAL_NAME_TO_FIELD = {
    "TOOL_PROVIDER": "tool_provider",
    "OPENCLAW_MODE": "mode",
    "OPENCLAW_DRY_RUN": "dry_run",
    "OPENCLAW_CLI_PATH": "cli_path",
    "OPENCLAW_CLI": "cli_path",
    "OPENCLAW_CLI_AGENT_ID": "cli_agent_id",
    "OPENCLAW_CLI_MODEL": "cli_model",
    "OPENCLAW_CLI_SESSION_KEY": "cli_session_key",
    "OPENCLAW_CLI_LOCAL": "cli_local",
    "OPENCLAW_CLI_DELIVER": "cli_deliver",
    "OPENCLAW_CLI_JSON": "cli_json",
    "OPENCLAW_WORKSPACE": "workspace",
    "OPENCLAW_WORKDIR": "workspace",
    "OPENCLAW_TIMEOUT_SECONDS": "timeout_seconds",
    "OPENCLAW_HTTP_BASE_URL": "http_base_url",
    "OPENCLAW_API_URL": "http_base_url",
    "OPENCLAW_GATEWAY_WS_URL": "gateway_ws_url",
    "OPENCLAW_WS_URL": "gateway_ws_url",
    "OPENCLAW_GATEWAY_URL": "gateway_url",
    "OPENCLAW_AUTH_TOKEN": "auth_token",
    "OPENCLAW_TOKEN": "auth_token",
    "OPENCLAW_CLIENT_ROLE": "client_role",
    "OPENCLAW_SESSION_NAME": "session_name",
    "OPENCLAW_LOG_RAW_OUTPUT": "log_raw_output",
    "OPENCLAW_MAX_TTS_CHARS": "max_tts_chars",
    "OPENCLAW_MAX_UI_CHARS": "max_ui_chars",
    "OPENCLAW_LOG_DIR": "log_dir",
    "OPENCLAW_SYLPHOS_LOG_PATH": "sylphos_log_path",
    "OPENCLAW_AUDIT_LOG_PATH": "audit_log_path",
}


def load_openclaw_bridge_config() -> OpenClawBridgeConfig:
    """Load OpenClaw bridge settings from the same layered config as Runtime.

    The Runtime loader already merges defaults, root/package/project-local
    project-root ``local_config.py``, and environment
    variables.  Reusing it here keeps ``load_config().OPENCLAW_DRY_RUN`` and
    ``load_openclaw_bridge_config().dry_run`` synchronized.
    """

    values: dict[str, Any] = {
        "tool_provider": TOOL_PROVIDER,
        "mode": OPENCLAW_MODE,
        "dry_run": OPENCLAW_DRY_RUN,
        "cli_path": OPENCLAW_CLI_PATH,
        "cli_agent_id": OPENCLAW_CLI_AGENT_ID,
        "cli_model": OPENCLAW_CLI_MODEL,
        "cli_session_key": OPENCLAW_CLI_SESSION_KEY,
        "cli_local": OPENCLAW_CLI_LOCAL,
        "cli_deliver": OPENCLAW_CLI_DELIVER,
        "cli_json": OPENCLAW_CLI_JSON,
        "workspace": OPENCLAW_WORKSPACE,
        "timeout_seconds": OPENCLAW_TIMEOUT_SECONDS,
        "http_base_url": OPENCLAW_HTTP_BASE_URL,
        "gateway_ws_url": OPENCLAW_GATEWAY_WS_URL,
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

    from sylphos.config.loader import load_config

    runtime_config = load_config()
    alias_names = {
        "OPENCLAW_CLI",
        "OPENCLAW_WORKDIR",
        "OPENCLAW_API_URL",
        "OPENCLAW_WS_URL",
        "OPENCLAW_TOKEN",
    }
    for key, field in _LOCAL_NAME_TO_FIELD.items():
        if key not in alias_names and hasattr(runtime_config, key):
            values[field] = getattr(runtime_config, key)

    def apply_alias(preferred_name: str, alias_name: str, field: str, default_preferred: Any, default_alias: Any) -> None:
        preferred = getattr(runtime_config, preferred_name, default_preferred)
        alias = getattr(runtime_config, alias_name, default_alias)
        if preferred != default_preferred:
            values[field] = preferred
        elif alias != default_alias:
            values[field] = alias
        else:
            values[field] = preferred

    apply_alias("OPENCLAW_CLI_PATH", "OPENCLAW_CLI", "cli_path", OPENCLAW_CLI_PATH, OPENCLAW_CLI)
    apply_alias("OPENCLAW_WORKSPACE", "OPENCLAW_WORKDIR", "workspace", OPENCLAW_WORKSPACE, OPENCLAW_WORKDIR)
    apply_alias("OPENCLAW_HTTP_BASE_URL", "OPENCLAW_API_URL", "http_base_url", OPENCLAW_HTTP_BASE_URL, OPENCLAW_API_URL)
    apply_alias("OPENCLAW_GATEWAY_WS_URL", "OPENCLAW_WS_URL", "gateway_ws_url", OPENCLAW_GATEWAY_WS_URL, OPENCLAW_WS_URL)
    apply_alias("OPENCLAW_AUTH_TOKEN", "OPENCLAW_TOKEN", "auth_token", OPENCLAW_AUTH_TOKEN, OPENCLAW_TOKEN)
    values.update(
        {
            "tool_provider": os.getenv("TOOL_PROVIDER", values["tool_provider"]),
            "mode": os.getenv("OPENCLAW_MODE", values["mode"]),
            "dry_run": _env_bool("OPENCLAW_DRY_RUN", bool(values["dry_run"])),
            "cli_path": os.getenv("OPENCLAW_CLI_PATH", os.getenv("OPENCLAW_CLI", str(values["cli_path"]))),
            "cli_agent_id": _optional_text("OPENCLAW_CLI_AGENT_ID", values["cli_agent_id"]),
            "cli_model": _optional_text("OPENCLAW_CLI_MODEL", values["cli_model"]),
            "cli_session_key": _optional_text("OPENCLAW_CLI_SESSION_KEY", values["cli_session_key"]),
            "cli_local": _env_bool("OPENCLAW_CLI_LOCAL", bool(values["cli_local"])),
            "cli_deliver": _env_bool("OPENCLAW_CLI_DELIVER", bool(values["cli_deliver"])),
            "cli_json": _env_bool("OPENCLAW_CLI_JSON", bool(values["cli_json"])),
            "workspace": _optional_text("OPENCLAW_WORKSPACE", _optional_text("OPENCLAW_WORKDIR", values["workspace"])),
            "timeout_seconds": _env_float("OPENCLAW_TIMEOUT_SECONDS", float(values["timeout_seconds"])),
            "http_base_url": os.getenv("OPENCLAW_HTTP_BASE_URL", os.getenv("OPENCLAW_API_URL", str(values["http_base_url"]))),
            "gateway_ws_url": os.getenv("OPENCLAW_GATEWAY_WS_URL", os.getenv("OPENCLAW_WS_URL", str(values["gateway_ws_url"]))),
            "gateway_url": _optional_text("OPENCLAW_GATEWAY_URL", values["gateway_url"]),
            "auth_token": _optional_text("OPENCLAW_AUTH_TOKEN", _optional_text("OPENCLAW_TOKEN", values["auth_token"])),
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

    # Compatibility for early bridge configs that only set OPENCLAW_GATEWAY_URL.
    if values["gateway_url"] and "OPENCLAW_HTTP_BASE_URL" not in os.environ:
        values["http_base_url"] = _gateway_url_to_http_base_url(values["gateway_url"]) or values["http_base_url"]

    Path(values["log_dir"]).mkdir(parents=True, exist_ok=True)
    return OpenClawBridgeConfig(**values)
