from __future__ import annotations

"""Interactive CLI smoke test for SylphosOpenClawBridge."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sylphos.executor.openclaw_bridge import SylphosOpenClawBridge
from sylphos.executor.openclaw_config import load_openclaw_bridge_config


def _short(text: str | None, limit: int = 500) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[: limit - 16].rstrip()}… [truncated]"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sylphos OpenClaw Bridge Test")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode for submitted requests.")
    parser.add_argument("--execute", action="store_true", help="Force actual CLI execution when mode=cli.")
    args = parser.parse_args()

    config = load_openclaw_bridge_config()
    bridge = SylphosOpenClawBridge(config)
    forced_dry_run = True if args.dry_run else False if args.execute else None

    print("Sylphos OpenClaw Bridge Test")
    print("输入 q 退出")
    print(f"[logs] sylphos={Path(config.sylphos_log_path)} audit={Path(config.audit_log_path)}")
    print(f"[health] {bridge.health_check()}")

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            return 0
        if text.lower() in {"q", "quit", "exit"}:
            print("退出。")
            return 0
        if not text:
            continue

        result = bridge.submit_text(text, source="debug", dry_run=forced_dry_run)
        print(f"[request_id] {result.request_id}")
        print(f"[ok] {result.ok}")
        print(f"[status] {result.status}")
        print(f"[speak] {result.speak_text}")
        print(f"[ui] {_short(result.ui_text)}")
        if result.needs_confirmation:
            print(f"[confirmation] {result.confirmation_prompt}")
        print(f"[stdout] {_short(result.raw_stdout)}")
        print(f"[stderr] {_short(result.raw_stderr)}")
        print(f"[logs] sylphos={Path(config.sylphos_log_path)} audit={Path(config.audit_log_path)}")


if __name__ == "__main__":
    raise SystemExit(main())
