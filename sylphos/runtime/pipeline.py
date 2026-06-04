from __future__ import annotations

"""Minimal ASR text -> OpenClaw -> TTS boundary helpers.

This module intentionally does not import SenseVoice or CosyVoice.  It exposes
small extension points that let the runtime send transcribed text to OpenClaw
and pass ``OpenClawResult.spoken_text`` to whichever TTS handler is active.
"""

from sylphos.llm.base import BaseAgentClient
from sylphos.llm.openclaw_client import create_openclaw_client
from sylphos.llm.types import OpenClawResult


def handle_transcribed_text(text: str, *, client: BaseAgentClient | None = None) -> OpenClawResult:
    """Send SenseVoice/Sylphos ASR text to OpenClaw and return its result.

    Intended chain:
        ASR text in -> OpenClaw client -> OpenClawResult -> TTS speak(spoken_text)
    """

    active_client = client or create_openclaw_client()
    return active_client.ask(text)


async def ahandle_transcribed_text(text: str, *, client: BaseAgentClient | None = None) -> OpenClawResult:
    """Async variant for future streaming/WebSocket runtime paths."""

    active_client = client or create_openclaw_client()
    return await active_client.aask(text)
