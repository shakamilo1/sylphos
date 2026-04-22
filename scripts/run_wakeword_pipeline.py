from __future__ import annotations

"""Wakeword 正式运行入口。"""

import logging

from scripts.runtime_bootstrap import create_runtime_stack, start_runtime_stack, stop_runtime_stack


def main() -> None:
    """组装并启动 wakeword + recorder 的事件化运行链路。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    stack = create_runtime_stack()

    start_runtime_stack(stack)
    print("AudioHub running. Ctrl+C to stop.")
    print("输入 r + 回车：手动恢复唤醒监听")

    try:
        while True:
            cmd = input().strip().lower()
            if cmd == "r":
                stack["orchestrator"].resume_wakeword()
    except KeyboardInterrupt:
        pass
    finally:
        stop_runtime_stack(stack)


if __name__ == "__main__":
    main()
