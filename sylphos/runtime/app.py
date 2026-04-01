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


@dataclass
class RuntimeConfig:
    """Sylphos 运行时的基础配置（后续可以慢慢扩展）."""
    name: str = "Sylphos"
    version: str = "0.1.0"
    log_level: int = logging.INFO


class RuntimeApp:
    """
    Sylphos Runtime 的最小骨架。

    未来你会在这里：
    - 初始化 LLM 客户端
    - 初始化 MCP 客户端
    - 启动事件循环 / 消息路由
    """

    def __init__(self, config: Optional[RuntimeConfig] = None) -> None:
        self.config = config or RuntimeConfig()
        self.log = logging.getLogger("sylphos.runtime")

    def start(self) -> None:
        """启动运行时（当前版本：打印日志 + 跑一遍 MCP demo）."""
        self.log.info("Starting %s runtime v%s", self.config.name, self.config.version)
        self.log.info("Runtime is up. (minimal stub)")
        self.log.info("Running MCP demo roundtrip ...")
        self._demo_mcp_roundtrip()

    def _demo_mcp_roundtrip(self) -> None:
        """调用 sylphos.mcp.core.demo_run_once 并打印结果."""
        resp = demo_run_once()
        self.log.info("MCP demo response: %r", resp)

    def run_forever(self) -> None:
        """
        模拟一个“守护进程式”的主循环。
        后续可以替换为 asyncio / 消息队列等。
        """
        self.log.info("Entering main loop. Press Ctrl+C to exit.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            self.log.info("KeyboardInterrupt received, shutting down ...")
            self.shutdown()

    def shutdown(self) -> None:
        """清理资源并优雅退出."""
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
    """作为模块入口的 main 函数."""
    config = RuntimeConfig()
    configure_logging(config.log_level)

    app = RuntimeApp(config=config)
    app.start()
    app.run_forever()


if __name__ == "__main__":
    main()
