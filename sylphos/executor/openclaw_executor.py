from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess

from sylphos.runtime.context import RuntimeContext
from sylphos.runtime.events import ToolExecutionRequested

_HIGH_RISK = re.compile(r"(?i)(rm\s+-rf|del\s+/[sq]|format|mkfs|system32|/etc/|token|password|sudo|注册表|删除全部|清空)")


class DummyExecutor:
    name = "dummy"
    def __init__(self) -> None: self.logger = logging.getLogger(self.__class__.__name__)
    def execute(self, request: ToolExecutionRequested, context: RuntimeContext) -> dict:
        command = request.text or request.parameters.get("command") or ""
        self.logger.info("DummyExecutor executing: %s", command)
        return {"ok": True, "status": "dummy_completed", "command": command, "message": f"已模拟执行：{command}"}
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("DummyExecutor cancel requested")
    def close(self): pass


class OpenClawExecutor:
    name = "openclaw"
    def __init__(self, *, cli: str = "openclaw", timeout_seconds: int = 60, dry_run: bool = True) -> None:
        self.cli = cli; self.timeout_seconds = timeout_seconds; self.dry_run = dry_run
        self.logger = logging.getLogger(self.__class__.__name__)
        self._process: subprocess.Popen | None = None
    def safety_check(self, command: str) -> tuple[bool, str | None]:
        if _HIGH_RISK.search(command): return False, "high-risk command blocked by OpenClawExecutor safety_check"
        return True, None
    def execute(self, request: ToolExecutionRequested, context: RuntimeContext) -> dict:
        command = request.text or request.parameters.get("command") or request.parameters.get("text") or ""
        allowed, reason = self.safety_check(command)
        if not allowed: raise PermissionError(reason)
        if self.dry_run or shutil.which(self.cli) is None:
            self.logger.info("OpenClaw dry-run/CLI missing command=%s cli=%s", command, self.cli)
            return {"ok": True, "status": "openclaw_dry_run", "command": command, "message": f"OpenClaw dry-run：{command}"}
        args = [self.cli, command]
        self.logger.info("Running OpenClaw CLI: %s", args)
        completed = subprocess.run(args, text=True, capture_output=True, timeout=self.timeout_seconds, check=False)
        result = {"ok": completed.returncode == 0, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "command": command}
        if completed.returncode != 0:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        return result
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    def cancel(self):
        self.logger.info("OpenClawExecutor cancel requested")
        if self._process and self._process.poll() is None: self._process.terminate()
    def close(self): self.cancel()
