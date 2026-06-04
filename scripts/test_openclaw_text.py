#!/usr/bin/env python
from __future__ import annotations

"""Manual OpenClaw text roundtrip.

Usage:
    python scripts/test_openclaw_text.py "打开 Sylphos 项目"
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sylphos.llm.openclaw_client import OpenClawError, create_openclaw_client


def main() -> int:
    parser = argparse.ArgumentParser(description="Send text to OpenClaw and print raw/spoken replies.")
    parser.add_argument("text", help="User text to send to OpenClaw")
    args = parser.parse_args()

    print("User text:")
    print(args.text)
    print()

    client = create_openclaw_client()
    try:
        result = client.ask(args.text)
    except OpenClawError as exc:
        print(f"OpenClaw error: {exc}", file=sys.stderr)
        return 1

    print("OpenClaw raw reply:")
    print(result.raw_text)
    print()
    print("Spoken reply:")
    print(result.spoken_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
