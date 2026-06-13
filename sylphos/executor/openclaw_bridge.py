from __future__ import annotations

"""Source-agnostic bridge between Sylphos and OpenClaw executor backends."""

import json
import logging
import re
import shutil
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from dataclasses import asdict, replace
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

from .openclaw_config import OPENCLAW_HTTP_BASE_URL as DEFAULT_OPENCLAW_HTTP_BASE_URL
from .openclaw_config import OpenClawBridgeConfig, load_openclaw_bridge_config
from .openclaw_models import OpenClawRequest, OpenClawBridgeResult, utc_now_iso

_SECRET_KEY_RE = re.compile(r"(token|password|passwd|secret|api[_-]?key|auth|credential)", re.IGNORECASE)
_SECRET_VALUE_RE = re.compile(
    r"(?i)(token|password|passwd|secret|api[_-]?key|authorization|bearer)(\s*[:=]\s*|\s+)[^\s,;]+"
)
_HIGH_RISK_RE = re.compile(
    r"(?i)(\brm\s+-rf\b|\bdel\s+/[sq]\b|delete\s+all\s+files|remove\s+project\s+directory|"
    r"erase\s+workspace|wipe\s+folder|clear\s+directory|purge\s+files|destroy\s+files|"
    r"删除|覆写|覆盖|format\s+|mkfs|system32|/etc/|"
    r"ssh[_ -]?key|id_rsa|\.ssh|token|password|passwd|secret|api[_-]?key|"
    r"curl\b.*\|\s*(sh|bash)|wget\b.*\|\s*(sh|bash)|下载.*执行|send\s+email|发送(邮件|消息)|"
    r"修改系统配置|registry|注册表|sudo\s+|chmod\s+777|未知脚本)"
)
_MEDIUM_RISK_RE = re.compile(
    r"(?i)(创建|新建|写入|修改|编辑|保存|执行|运行|安装|pip\s+install|npm\s+install|"
    r"git\s+(commit|push|pull|merge)|touch\s+|mkdir\s+|python\s+|node\s+|pytest|命令)"
)
_LOW_RISK_RE = re.compile(r"(?i)(查询|查看|打开|状态|读取|list|show|open|status|read|检查|搜索|find)")


def classify_risk(text: str) -> str:
    """Classify a natural-language task into low, medium, or high risk."""

    normalized = text.strip()
    if _HIGH_RISK_RE.search(normalized):
        return "high"
    if _MEDIUM_RISK_RE.search(normalized):
        return "medium"
    if _LOW_RISK_RE.search(normalized):
        return "low"
    return "medium"


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 20)].rstrip()}… [truncated]"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("<redacted>" if _SECRET_KEY_RE.search(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE_RE.sub(r"\1\2<redacted>", value)
    return value


def _duration_ms(started_at: datetime, finished_at: datetime) -> int:
    return int((finished_at - started_at).total_seconds() * 1000)


class SylphosOpenClawBridge:
    """Submit source-agnostic Sylphos text requests to OpenClaw and structure output."""

    def __init__(self, config: Any = None, *, agent_client: BaseAgentClient | None = None) -> None:
        self.config = self._coerce_config(config)
        self.agent_client = agent_client
        self.log_path = Path(self.config.sylphos_log_path)
        self.audit_log_path = Path(self.config.audit_log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = self._build_logger()
        self.logger.info(
            "SylphosOpenClawBridge initialized provider=%s mode=%s dry_run=%s workspace=%s",
            self.config.tool_provider,
            self.config.mode,
            self.config.dry_run,
            self.config.workspace,
        )

    def submit_text(
        self,
        text: str,
        *,
        source: str = "debug",
        context: dict | None = None,
        dry_run: bool | None = None,
    ) -> OpenClawBridgeResult:
        """Create an OpenClawRequest from text and submit it through the bridge."""

        request = OpenClawRequest(
            request_id=str(uuid.uuid4()),
            source=source,
            text=text,
            context=context or {},
            workspace=self.config.workspace,
            dry_run=self.config.dry_run if dry_run is None else dry_run,
            created_at=utc_now_iso(),
        )
        return self.submit_request(request)

    def submit_request(self, request: OpenClawRequest) -> OpenClawBridgeResult:
        """Submit a structured request, returning a structured result without crashing Sylphos."""

        started = datetime.now(UTC)
        started_at = started.isoformat()
        self.logger.info(
            "OpenClaw request start request_id=%s source=%s mode=%s dry_run=%s risk=%s",
            request.request_id,
            request.source,
            self.config.mode,
            request.dry_run,
            classify_risk(request.text),
        )

        risk = classify_risk(request.text)
        confirmed = request.context.get("confirmed") is True
        if risk == "high" and not confirmed:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="needs_confirmation",
                text="High-risk request requires user confirmation before OpenClaw execution.",
                needs_confirmation=True,
                confirmation_prompt="该请求可能涉及高风险操作。请确认是否允许 OpenClaw 执行？",
                started_at=started_at,
            )
            self._finish_result(result, started)
            self._finalize_result(request, result)
            return result

        if request.dry_run:
            result = self._run_dry_request(request, started_at)
            self._finish_result(result, started)
            self._finalize_result(request, result)
            return result

        if self.config.mode == "cli":
            result = self._run_cli_request(request, started, started_at)
        elif self.config.mode in {"http", "api", "gateway"}:
            result = self._run_http_gateway_request(request, started, started_at)
        elif self.config.mode in {"websocket", "ws"}:
            result = self._run_websocket_request(request, started_at)
            self._finish_result(result, started)
        else:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="failed",
                error=f"Unsupported OPENCLAW_MODE: {self.config.mode}",
                started_at=started_at,
            )
            self._finish_result(result, started)

        self._finalize_result(request, result)
        return result

    def health_check(self) -> dict:
        """Return bridge health without sending user tasks to OpenClaw."""

        self.logger.info("OpenClaw bridge health_check mode=%s", self.config.mode)
        if self.config.mode == "cli":
            executable = shutil.which(self.config.cli_path)
            return {
                "ok": executable is not None,
                "provider": self.config.tool_provider,
                "mode": self.config.mode,
                "dry_run": self.config.dry_run,
                "cli_path": self.config.cli_path,
                "cli_found": executable is not None,
                "resolved_cli_path": executable,
                "workspace": self.config.workspace,
                "timeout_seconds": self.config.timeout_seconds,
                "sylphos_log_path": str(self.log_path),
                "audit_log_path": str(self.audit_log_path),
            }
        if self.config.mode in {"http", "gateway"}:
            settings = self._build_http_settings()
            return {
                "ok": True,
                "provider": self.config.tool_provider,
                "mode": self.config.mode,
                "base_url": settings.base_url,
                "model": settings.model,
                "session_key": settings.session_key,
                "message_channel": settings.message_channel,
                "token_present": bool(settings.token),
                "status": "configured",
                "message": "OpenClaw Gateway HTTP mode reuses the PR #15 OpenClawHTTPClient.",
            }
        if self.config.mode in {"websocket", "ws"}:
            return {
                "ok": False,
                "provider": self.config.tool_provider,
                "mode": self.config.mode,
                "gateway_ws_url": self.config.gateway_ws_url,
                "token_present": bool(self.config.auth_token),
                "status": "not_implemented",
                "message": "Typed WebSocket mode is reserved for the future OpenClaw protocol.",
            }
        return {"ok": False, "provider": self.config.tool_provider, "mode": self.config.mode, "status": "invalid_mode"}

    def _coerce_config(self, config: Any) -> OpenClawBridgeConfig:
        if config is None:
            return load_openclaw_bridge_config()
        if isinstance(config, OpenClawBridgeConfig):
            return config
        data = asdict(load_openclaw_bridge_config()) | {
            "tool_provider": getattr(config, "TOOL_PROVIDER", getattr(config, "tool_provider", None)),
            "mode": getattr(config, "OPENCLAW_MODE", getattr(config, "mode", None)),
            "dry_run": getattr(config, "OPENCLAW_DRY_RUN", getattr(config, "dry_run", None)),
            "cli_path": getattr(config, "OPENCLAW_CLI_PATH", getattr(config, "cli_path", None)),
            "cli_agent_id": getattr(config, "OPENCLAW_CLI_AGENT_ID", getattr(config, "cli_agent_id", None)),
            "cli_model": getattr(config, "OPENCLAW_CLI_MODEL", getattr(config, "cli_model", None)),
            "cli_session_key": getattr(config, "OPENCLAW_CLI_SESSION_KEY", getattr(config, "cli_session_key", None)),
            "cli_local": getattr(config, "OPENCLAW_CLI_LOCAL", getattr(config, "cli_local", None)),
            "cli_deliver": getattr(config, "OPENCLAW_CLI_DELIVER", getattr(config, "cli_deliver", None)),
            "cli_json": getattr(config, "OPENCLAW_CLI_JSON", getattr(config, "cli_json", None)),
            "workspace": getattr(config, "OPENCLAW_WORKSPACE", getattr(config, "workspace", None)),
            "timeout_seconds": getattr(config, "OPENCLAW_TIMEOUT_SECONDS", getattr(config, "timeout_seconds", None)),
            "http_base_url": getattr(config, "OPENCLAW_HTTP_BASE_URL", getattr(config, "http_base_url", None)),
            "gateway_ws_url": getattr(config, "OPENCLAW_GATEWAY_WS_URL", getattr(config, "gateway_ws_url", None)),
            "gateway_url": getattr(config, "OPENCLAW_GATEWAY_URL", getattr(config, "gateway_url", None)),
            "auth_token": getattr(config, "OPENCLAW_AUTH_TOKEN", getattr(config, "auth_token", None)),
            "client_role": getattr(config, "OPENCLAW_CLIENT_ROLE", getattr(config, "client_role", None)),
            "session_name": getattr(config, "OPENCLAW_SESSION_NAME", getattr(config, "session_name", None)),
            "log_raw_output": getattr(config, "OPENCLAW_LOG_RAW_OUTPUT", getattr(config, "log_raw_output", None)),
            "max_tts_chars": getattr(config, "OPENCLAW_MAX_TTS_CHARS", getattr(config, "max_tts_chars", None)),
            "max_ui_chars": getattr(config, "OPENCLAW_MAX_UI_CHARS", getattr(config, "max_ui_chars", None)),
            "log_dir": getattr(config, "OPENCLAW_LOG_DIR", getattr(config, "log_dir", None)),
            "sylphos_log_path": getattr(config, "OPENCLAW_SYLPHOS_LOG_PATH", getattr(config, "sylphos_log_path", None)),
            "audit_log_path": getattr(config, "OPENCLAW_AUDIT_LOG_PATH", getattr(config, "audit_log_path", None)),
        }
        clean_data = {key: value for key, value in data.items() if value is not None}
        return OpenClawBridgeConfig(**clean_data)

    def _build_logger(self) -> logging.Logger:
        logger = logging.getLogger("sylphos.openclaw_bridge")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == self.log_path.resolve() for handler in logger.handlers):
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            logger.addHandler(handler)
        return logger

    def _run_dry_request(self, request: OpenClawRequest, started_at: str) -> OpenClawBridgeResult:
        action = self._build_dry_run_action(request)
        return OpenClawBridgeResult(
            request_id=request.request_id,
            ok=True,
            status="dry_run",
            text="Dry run completed. OpenClaw was not executed.",
            ui_text="Dry run completed. OpenClaw was not executed.",
            actions=[action],
            commands_run=[action],
            started_at=started_at,
        )

    def _build_dry_run_action(self, request: OpenClawRequest) -> dict[str, Any]:
        if self.config.mode == "cli":
            return {
                "type": "openclaw_cli",
                "command": _redact(self._build_cli_command(request)),
                "dry_run": True,
                "workspace": request.workspace,
            }
        return {
            "type": "openclaw_gateway",
            "mode": self.config.mode,
            "dry_run": True,
            "workspace": request.workspace,
        }

    def _run_cli_request(self, request: OpenClawRequest, started: datetime, started_at: str) -> OpenClawBridgeResult:
        command = self._build_cli_command(request)
        executable = shutil.which(command[0])
        if executable is None:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="failed",
                error=f"OpenClaw CLI command not found: {command[0]}",
                started_at=started_at,
            )
            self._finish_result(result, started)
            return result

        command[0] = executable

        cwd = request.workspace if request.workspace else None
        self.logger.info(
            "Executing OpenClaw CLI request_id=%s command=%s cwd=%s timeout=%s",
            request.request_id,
            _redact(command),
            cwd,
            self.config.timeout_seconds,
        )
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.timeout_seconds,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            parsed = self._parse_openclaw_output(stdout, stderr)
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=completed.returncode == 0,
                status=parsed["status"] or ("success" if completed.returncode == 0 else "failed"),
                text=parsed["text"],
                speak_text=parsed.get("speak_text"),
                ui_text=parsed["ui_text"],
                actions=parsed["actions"],
                files_changed=parsed["files_changed"],
                commands_run=[
                    {"command": _redact(command), "exit_code": completed.returncode, "workspace": request.workspace},
                    *parsed["commands_run"],
                ],
                raw_stdout=stdout if self.config.log_raw_output else None,
                raw_stderr=stderr if self.config.log_raw_output else None,
                exit_code=completed.returncode,
                error=parsed.get("error") if completed.returncode == 0 else (parsed.get("error") or stderr.strip() or "OpenClaw CLI exited with a non-zero code."),
                started_at=started_at,
            )
            self._finish_result(result, started)
            return result
        except subprocess.TimeoutExpired as exc:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="timeout",
                raw_stdout=exc.stdout if isinstance(exc.stdout, str) else None,
                raw_stderr=exc.stderr if isinstance(exc.stderr, str) else None,
                error=f"OpenClaw CLI timed out after {self.config.timeout_seconds} seconds.",
                commands_run=[{"command": _redact(command), "timeout": True, "workspace": request.workspace}],
                started_at=started_at,
            )
            self._finish_result(result, started)
            self.logger.warning("OpenClaw CLI timeout request_id=%s", request.request_id)
            return result
        except Exception as exc:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="failed",
                error=f"OpenClaw CLI execution failed: {exc}",
                commands_run=[{"command": _redact(command), "workspace": request.workspace}],
                started_at=started_at,
            )
            self._finish_result(result, started)
            self.logger.exception("OpenClaw CLI unexpected error request_id=%s", request.request_id)
            return result

    def _run_http_gateway_request(
        self, request: OpenClawRequest, started: datetime, started_at: str
    ) -> OpenClawBridgeResult:
        settings = self._build_http_settings()
        client = self.agent_client or create_openclaw_client(settings)
        session_key = str(request.context.get("session_key") or settings.session_key)
        self.logger.info(
            "Executing OpenClaw HTTP Gateway request_id=%s base_url=%s model=%s session_key=%s token_present=%s",
            request.request_id,
            settings.base_url,
            settings.model,
            session_key,
            bool(settings.token),
        )
        try:
            client_result = client.ask(request.text, session_key=session_key)
            metadata = dict(getattr(client_result, "metadata", {}) or {})
            text = getattr(client_result, "raw_text", None) or getattr(client_result, "spoken_text", None)
            spoken_text = getattr(client_result, "spoken_text", None)
            status = str(getattr(client_result, "status", "success") or "success")
            ok = self._is_success_status(status)
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=ok,
                status=status,
                text=text,
                speak_text=spoken_text if ok else None,
                ui_text=_clip(text, self.config.max_ui_chars),
                actions=metadata.get("actions") if isinstance(metadata.get("actions"), list) else [],
                files_changed=metadata.get("files_changed") if isinstance(metadata.get("files_changed"), list) else [],
                commands_run=metadata.get("commands_run") if isinstance(metadata.get("commands_run"), list) else [],
                raw_stdout=text if self.config.log_raw_output else None,
                raw_stderr=None,
                exit_code=None,
                error=None if ok else str(metadata.get("error") or text or f"OpenClaw client returned status: {status}"),
                started_at=started_at,
            )
            self._finish_result(result, started)
            return result
        except OpenClawTimeoutError as exc:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="timeout",
                error=str(exc),
                started_at=started_at,
            )
        except (OpenClawAuthError, OpenClawConnectionError, OpenClawResponseError) as exc:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="failed",
                error=str(exc),
                started_at=started_at,
            )
        except Exception as exc:
            result = OpenClawBridgeResult(
                request_id=request.request_id,
                ok=False,
                status="failed",
                error=f"OpenClaw Gateway execution failed: {exc}",
                started_at=started_at,
            )
            self.logger.exception("OpenClaw Gateway unexpected error request_id=%s", request.request_id)
        self._finish_result(result, started)
        return result

    @staticmethod
    def _is_success_status(status: str) -> bool:
        return status.strip().lower() in {"ok", "success", "completed"}

    def _run_websocket_request(self, request: OpenClawRequest, started_at: str) -> OpenClawBridgeResult:
        return OpenClawBridgeResult(
            request_id=request.request_id,
            ok=False,
            status="failed",
            text="OpenClaw typed WebSocket mode is not implemented yet.",
            ui_text="OpenClaw typed WebSocket mode is reserved until the protocol is confirmed.",
            error="WebSocket mode is reserved for future OpenClaw streaming integration.",
            started_at=started_at,
        )

    def _build_http_settings(self) -> OpenClawSettings:
        settings = get_openclaw_settings()
        base_url = self.config.http_base_url or settings.base_url
        if self.config.gateway_url and base_url == DEFAULT_OPENCLAW_HTTP_BASE_URL:
            base_url = self._gateway_url_as_http_base_url(self.config.gateway_url) or base_url
        return replace(
            settings,
            base_url=base_url,
            token=self.config.auth_token if self.config.auth_token is not None else settings.token,
            session_key=self.config.session_name or settings.session_key,
            timeout_seconds=self.config.timeout_seconds,
            max_spoken_chars=self.config.max_tts_chars,
        )


    @staticmethod
    def _gateway_url_as_http_base_url(gateway_url: str | None) -> str | None:
        if not gateway_url:
            return None
        if gateway_url.startswith("ws://"):
            return "http://" + gateway_url.removeprefix("ws://")
        if gateway_url.startswith("wss://"):
            return "https://" + gateway_url.removeprefix("wss://")
        return gateway_url

    def _build_cli_command(self, request: OpenClawRequest) -> list[str]:
        """Build the OpenClaw CLI agent command for a single natural-language turn."""

        timeout_seconds = max(1, int(self.config.timeout_seconds))
        command = [
            self.config.cli_path,
            "agent",
            "--message",
            request.text,
        ]
        if self.config.cli_json:
            command.append("--json")
        command.extend(["--timeout", str(timeout_seconds)])

        session_key = request.context.get("session_key") or self.config.cli_session_key
        if session_key:
            command.extend(["--session-key", str(session_key)])
        if self.config.cli_agent_id:
            command.extend(["--agent", self.config.cli_agent_id])
        if self.config.cli_model:
            command.extend(["--model", self.config.cli_model])
        if self.config.cli_local is True:
            command.append("--local")
        if self.config.cli_deliver is True:
            command.append("--deliver")
        return command

    def _parse_openclaw_output(self, stdout: str | None, stderr: str | None) -> dict[str, Any]:
        stdout = stdout or ""
        stderr = stderr or ""
        data: dict[str, Any] = {}
        stripped = stdout.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                data = {}

        payload_text = None
        result = data.get("result")
        payloads = result.get("payloads") if isinstance(result, dict) else None
        if isinstance(payloads, list) and payloads:
            first_payload = payloads[0]
            if isinstance(first_payload, dict) and isinstance(first_payload.get("text"), str):
                payload_text = first_payload["text"]

        text = (
            payload_text
            or data.get("raw_text")
            or data.get("spoken_text")
            or data.get("speak_text")
            or data.get("text")
            or data.get("message")
            or data.get("summary")
            or stripped
            or stderr.strip()
            or None
        )
        speak_text = payload_text or data.get("spoken_text") or data.get("speak_text") or data.get("text") or data.get("summary")
        ui_text = payload_text or data.get("ui_text") or text
        return {
            "text": text,
            "speak_text": speak_text if isinstance(speak_text, str) else None,
            "ui_text": _clip(ui_text, self.config.max_ui_chars),
            "actions": data.get("actions") if isinstance(data.get("actions"), list) else [],
            "files_changed": data.get("files_changed") if isinstance(data.get("files_changed"), list) else [],
            "commands_run": data.get("commands_run") if isinstance(data.get("commands_run"), list) else [],
            "status": data.get("status") if isinstance(data.get("status"), str) else None,
            "error": data.get("error") if isinstance(data.get("error"), str) else None,
        }

    def _finish_result(self, result: OpenClawBridgeResult, started: datetime) -> None:
        finished = datetime.now(UTC)
        result.finished_at = finished.isoformat()
        result.duration_ms = _duration_ms(started, finished)

    def _finalize_result(self, request: OpenClawRequest, result: OpenClawBridgeResult) -> None:
        if not result.speak_text:
            result.speak_text = self._make_speak_text(result)
        if result.ui_text is None:
            result.ui_text = _clip(result.text or result.error, self.config.max_ui_chars)
        self._write_audit_log(request, result)
        self.logger.info(
            "OpenClaw request finished request_id=%s ok=%s status=%s exit_code=%s duration_ms=%s",
            request.request_id,
            result.ok,
            result.status,
            result.exit_code,
            result.duration_ms,
        )

    def _make_speak_text(self, result: OpenClawBridgeResult) -> str:
        """Create short TTS-safe speech text from a structured OpenClaw result."""

        limit = max(1, self.config.max_tts_chars)
        if result.needs_confirmation:
            return _clip(result.confirmation_prompt or "该请求需要确认。", limit) or "该请求需要确认。"
        if result.status == "timeout":
            return "OpenClaw 处理超时。"
        if result.status == "dry_run":
            return "模拟执行完成。"
        if not result.ok:
            error = result.error or result.text or "OpenClaw 执行失败。"
            return _clip(f"OpenClaw 执行失败：{error}", limit) or "OpenClaw 执行失败。"
        text = result.text or result.ui_text or "处理完成。"
        if len(text) <= limit:
            return text
        return "处理完成，详细结果已记录或显示。"

    def _write_audit_log(self, request: OpenClawRequest, result: OpenClawBridgeResult) -> None:
        summary = result.text or result.ui_text or result.error or result.status
        record = {
            "time": utc_now_iso(),
            "request_id": request.request_id,
            "source": request.source,
            "input_text": request.text,
            "executor": self.config.tool_provider,
            "mode": self.config.mode,
            "workspace": request.workspace,
            "dry_run": request.dry_run,
            "ok": result.ok,
            "status": result.status,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "summary": _clip(summary, self.config.max_ui_chars),
            "error": result.error,
        }
        safe_record = _redact(record)
        with self.audit_log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(safe_record, ensure_ascii=False) + "\n")
