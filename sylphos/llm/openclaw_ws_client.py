from __future__ import annotations

"""Reserved OpenClaw Gateway WebSocket / SDK client boundary."""

from collections.abc import Callable
from typing import Any

from sylphos.config.settings import OpenClawSettings, get_openclaw_settings
from sylphos.llm.base import BaseAgentClient
from sylphos.llm.types import OpenClawResult

OpenClawCallback = Callable[[Any], None]


class OpenClawWSClient(BaseAgentClient):
    """Stage-2 placeholder for typed WebSocket or SDK-backed OpenClaw runs.

    TODO:
    1. connect to Gateway typed WebSocket API;
    2. start agent run;
    3. stream events;
    4. collect final result;
    5. expose callbacks: on_event, on_tool_event, on_partial_text, on_final, on_error;
    6. support cancel(run_id);
    7. support interruption from Sylphos voice wake/stop command;
    8. support approval events in the future.

    If @openclaw/sdk is needed later, keep it outside Python dependencies via a
    bridge process: Sylphos Python -> local Node bridge -> @openclaw/sdk ->
    OpenClaw Gateway.
    """

    def __init__(
        self,
        *,
        settings: OpenClawSettings | None = None,
        on_event: OpenClawCallback | None = None,
        on_tool_event: OpenClawCallback | None = None,
        on_partial_text: OpenClawCallback | None = None,
        on_final: OpenClawCallback | None = None,
        on_error: OpenClawCallback | None = None,
    ) -> None:
        self.settings = settings or get_openclaw_settings()
        self.on_event = on_event
        self.on_tool_event = on_tool_event
        self.on_partial_text = on_partial_text
        self.on_final = on_final
        self.on_error = on_error

    def ask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        raise NotImplementedError("OpenClaw WebSocket client is reserved for the stage-2 streaming SDK integration.")

    async def aask(self, text: str, *, session_key: str | None = None) -> OpenClawResult:
        raise NotImplementedError("OpenClaw WebSocket client is reserved for the stage-2 streaming SDK integration.")

    def cancel(self, run_id: str) -> None:
        """Cancel an in-flight OpenClaw run once Gateway streaming is implemented."""
        raise NotImplementedError("OpenClaw run cancellation is reserved for the stage-2 WebSocket integration.")
