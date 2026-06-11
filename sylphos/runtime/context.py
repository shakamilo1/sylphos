from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from sylphos.runtime.events import RuntimeEvent
from sylphos.runtime.state import RuntimeState


@dataclass
class RuntimeContext:
    state: RuntimeState = RuntimeState.IDLE
    current_step: str | None = None
    current_event_id: str | None = None
    current_session_id: str = field(default_factory=lambda: str(uuid4()))
    last_event: RuntimeEvent | None = None
    last_audio_path: str | None = None
    last_asr_text: str | None = None
    last_user_utterance: str | None = None
    last_task_plan: dict[str, Any] | None = None
    last_tool_request: dict[str, Any] | None = None
    last_tool_result: dict[str, Any] | None = None
    interrupted_by_manual_override: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    def set_state(self, state: RuntimeState | str, step: str | None = None) -> None:
        self.state = RuntimeState.coerce(state)
        self.current_step = step

    def mark_event(self, event: RuntimeEvent, step: str | None = None) -> None:
        self.last_event = event
        self.current_event_id = event.event_id
        if step:
            self.current_step = step

    def reset_task(self) -> None:
        self.current_step = None
        self.current_event_id = None
        self.last_audio_path = None
        self.last_asr_text = None
        self.last_user_utterance = None
        self.last_task_plan = None
        self.last_tool_request = None
        self.last_tool_result = None
        self.interrupted_by_manual_override = False
