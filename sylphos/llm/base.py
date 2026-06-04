from __future__ import annotations

from typing import Protocol

from sylphos.llm.types import OpenClawResult


class BaseAgentClient(Protocol):
    """Protocol for task-executing agent clients used by Sylphos Runtime."""

    def ask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        """Send user text to an agent and return a speech-ready result."""
        ...

    async def aask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        """Async variant reserved for HTTP async clients and WebSocket agents."""
        ...
