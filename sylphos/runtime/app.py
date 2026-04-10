# sylphos/runtime/app.py
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

try:
    from rich.logging import RichHandler

    _HAS_RICH = True
except Exception:
    _HAS_RICH = False

from sylphos.mcp.core import demo_run_once
from sylphos.runtime.events import EventBus


@dataclass
class RuntimeConfig:
    """Sylphos 运行时的基础配置（后续可以慢慢扩展）."""

    name: str = "Sylphos"
    version: str = "0.2.0"
    log_level: int = logging.INFO


class RuntimeApp:
    """Sylphos Runtime 的轻量总线骨架。"""

    def __init__(self, config: Optional[RuntimeConfig] = None) -> None:
        self.config = config or RuntimeConfig()
        self.log = logging.getLogger("sylphos.runtime")
        self.event_bus = EventBus()
        self._started = False

    def start(self) -> None:
        """启动运行时（当前版本：日志 + EventBus + MCP demo）."""
        if self._started:
            self.log.warning("Runtime already started")
            return

        self.log.info("Starting %s runtime v%s", self.config.name, self.config.version)
        self.log.info("Runtime EventBus ready")
        self.log.info("Running MCP demo roundtrip ...")
        self._demo_mcp_roundtrip()
        self._started = True

    def _demo_mcp_roundtrip(self) -> None:
        """调用 sylphos.mcp.core.demo_run_once 并打印结果."""
        resp = demo_run_once()
        self.log.info("MCP demo response: %r", resp)

    def run_forever(self) -> None:
        self.log.info("Entering main loop. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.log.info("KeyboardInterrupt received, shutting down ...")
            self.shutdown()

    def shutdown(self) -> None:
        self._started = False
        self.log.info("Runtime shutdown complete.")


def configure_logging(level: int = logging.INFO) -> None:
    """配置基础日志输出格式."""
    if _HAS_RICH:
        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=True)],
        )
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


def main() -> None:
    config = RuntimeConfig()
    configure_logging(config.log_level)

    app = RuntimeApp(config=config)
    app.start()
    app.run_forever()


if __name__ == "__main__":
    main()
