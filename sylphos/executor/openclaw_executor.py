from __future__ import annotations

"""Runtime ToolExecutor adapters for OpenClaw.

The runtime executor delegates actual OpenClaw transport details to the existing
``SylphosOpenClawBridge`` so the event-driven Runtime does not duplicate or
fork the already-tested OpenClaw connection logic.
"""

import logging
from dataclasses import asdict, replace
from typing import Any

from sylphos.executor.openclaw_bridge import SylphosOpenClawBridge
from sylphos.executor.openclaw_config import OpenClawBridgeConfig, load_openclaw_bridge_config
from sylphos.executor.openclaw_models import OpenClawBridgeResult
from sylphos.runtime.context import RuntimeContext
from sylphos.runtime.events import ToolExecutionRequested


class OpenClawExecutionError(RuntimeError):
    """Raised when OpenClaw returns a structured non-success result."""

    def __init__(self, message: str, result: dict[str, Any]) -> None:
        super().__init__(message)
        self.result = result


class DummyExecutor:
    name = "dummy"

    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

    def execute(self, request: ToolExecutionRequested, context: RuntimeContext) -> dict:
        command = request.text or request.parameters.get("command") or request.parameters.get("text") or ""
        self.logger.info("DummyExecutor executing: %s", command)
        return {"ok": True, "status": "dummy_completed", "command": command, "message": f"已模拟执行：{command}"}

    def start(self) -> None: pass
    def stop(self) -> None: pass
    def pause(self) -> None: pass
    def resume(self) -> None: pass
    def cancel(self) -> None: self.logger.info("DummyExecutor cancel requested")
    def close(self) -> None: pass


class OpenClawExecutor:
    """OpenClaw ToolExecutor backed by the project OpenClaw bridge.

    ``OPENCLAW_MODE`` selects the transport in the bridge: ``cli``, ``http`` /
    ``api`` / ``gateway``, or the reserved ``websocket`` / ``ws`` mode.  This
    keeps OpenClaw as a pluggable executor instead of a Runtime core step.

    Current cancellation limitation: bridge calls are synchronous. ``cancel()``
    records the request for cancellation and is safe to call, but it cannot
    forcibly interrupt an in-flight ``subprocess.run`` or HTTP call until the
    bridge exposes cancellable handles. Timeouts remain enforced by the bridge.
    """

    name = "openclaw"

    def __init__(
        self,
        *,
        config: OpenClawBridgeConfig | None = None,
        bridge: SylphosOpenClawBridge | None = None,
    ) -> None:
        self.config = config or load_openclaw_bridge_config()
        self.bridge = bridge or SylphosOpenClawBridge(self.config)
        self.logger = logging.getLogger(self.__class__.__name__)
        self._cancel_requested = False

    def execute(self, request: ToolExecutionRequested, context: RuntimeContext) -> dict:
        self._cancel_requested = False
        command = request.text or request.parameters.get("command") or request.parameters.get("text") or ""
        if not command.strip():
            raise ValueError("OpenClawExecutor requires a non-empty command/text payload.")

        request_context = dict(request.parameters.get("context") or {})
        request_context.update(
            {
                "runtime_session_id": context.current_session_id,
                "runtime_event_id": request.event_id,
                "tool_request": request.payload,
            }
        )
        if request.parameters.get("confirmed") is True:
            request_context["confirmed"] = True
        if request.parameters.get("session_key"):
            request_context["session_key"] = request.parameters["session_key"]

        dry_run = request.parameters.get("dry_run")
        self.logger.info(
            "OpenClawExecutor dispatch mode=%s dry_run=%s command=%s",
            self.config.mode,
            self.config.dry_run if dry_run is None else dry_run,
            command,
        )
        result = self.bridge.submit_text(
            command,
            source=request.source or "runtime",
            context=request_context,
            dry_run=bool(dry_run) if dry_run is not None else None,
        )
        payload = self._result_to_runtime_payload(result, command)
        if not result.ok:
            raise OpenClawExecutionError(payload.get("message") or payload.get("error") or "OpenClaw execution failed", payload)
        return payload

    def _result_to_runtime_payload(self, result: OpenClawBridgeResult, command: str) -> dict[str, Any]:
        data = result.to_dict() if hasattr(result, "to_dict") else asdict(result)
        message = result.speak_text or result.ui_text or result.text or result.error or result.status
        data.update(
            {
                "ok": result.ok,
                "command": command,
                "message": message,
                "mode": self.config.mode,
                "dry_run": self.config.dry_run,
                "provider": "openclaw",
            }
        )
        return data

    def start(self) -> None: pass
    def stop(self) -> None: pass
    def pause(self) -> None: pass
    def resume(self) -> None: pass

    def cancel(self) -> None:
        self._cancel_requested = True
        self.logger.info(
            "OpenClawExecutor cancel requested; synchronous bridge calls cannot be force-killed yet and rely on timeout=%s",
            self.config.timeout_seconds,
        )

    def close(self) -> None:
        self.cancel()


class OpenClawCliExecutor(OpenClawExecutor):
    """OpenClaw executor pinned to CLI mode."""

    name = "openclaw_cli"

    def __init__(self, *, config: OpenClawBridgeConfig | None = None) -> None:
        cfg = config or load_openclaw_bridge_config()
        super().__init__(config=replace(cfg, mode="cli"))


class OpenClawApiExecutor(OpenClawExecutor):
    """OpenClaw executor pinned to HTTP/API gateway mode."""

    name = "openclaw_api"

    def __init__(self, *, config: OpenClawBridgeConfig | None = None) -> None:
        cfg = config or load_openclaw_bridge_config()
        super().__init__(config=replace(cfg, mode="http"))


class OpenClawWebSocketExecutor(OpenClawExecutor):
    """Reserved WebSocket executor adapter; bridge currently returns a typed failure."""

    name = "openclaw_websocket"

    def __init__(self, *, config: OpenClawBridgeConfig | None = None) -> None:
        cfg = config or load_openclaw_bridge_config()
        super().__init__(config=replace(cfg, mode="websocket"))
