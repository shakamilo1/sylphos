from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RuntimeEvent:
    """Base event for the in-process Sylphos Runtime event stream."""

    event_type: str
    source: str = "runtime"
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=utc_now)

    @property
    def created_at(self) -> datetime:  # backwards compatibility with older code
        return self.timestamp

    @property
    def payload(self) -> dict[str, Any]:
        data = {}
        for item in fields(self):
            if item.name not in {"event_type", "source", "metadata", "event_id", "timestamp"}:
                data[item.name] = getattr(self, item.name)
        data.update(self.metadata.get("payload", {}))
        return data


# Input events
@dataclass(slots=True)
class WakeWordDetected(RuntimeEvent):
    name: str = ""
    score: float = 0.0
    def __init__(self, name: str = "sylphos", score: float = 1.0, *, source: str = "wakeword", metadata: dict[str, Any] | None = None):
        super().__init__("wakeword.detected", source, metadata or {}); self.name = name; self.score = score

@dataclass(slots=True)
class AudioInputStarted(RuntimeEvent):
    def __init__(self, *, source: str = "audio", metadata: dict[str, Any] | None = None): super().__init__("audio.input.started", source, metadata or {})
@dataclass(slots=True)
class AudioInputCompleted(RuntimeEvent):
    audio_path: str | None = None
    def __init__(self, audio_path: str | None = None, *, source: str = "audio", metadata: dict[str, Any] | None = None): super().__init__("audio.input.completed", source, metadata or {}); self.audio_path = audio_path
@dataclass(slots=True)
class TextInputReceived(RuntimeEvent):
    text: str = ""
    def __init__(self, text: str, *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("text.input.received", source, metadata or {}); self.text = text
@dataclass(slots=True)
class HotkeyPressed(RuntimeEvent):
    key: str = ""
    def __init__(self, key: str, *, source: str = "hotkey", metadata: dict[str, Any] | None = None): super().__init__("hotkey.pressed", source, metadata or {}); self.key = key
@dataclass(slots=True)
class RemoteCommandReceived(RuntimeEvent):
    command: str = ""; payload_data: dict[str, Any] = field(default_factory=dict)
    def __init__(self, command: str, payload_data: dict[str, Any] | None = None, *, source: str = "remote", metadata: dict[str, Any] | None = None): super().__init__("remote.command.received", source, metadata or {}); self.command = command; self.payload_data = payload_data or {}

# Recording events
@dataclass(slots=True)
class RecordingRequested(RuntimeEvent):
    duration_seconds: float = 0.0; mode: str = "vad"
    def __init__(self, duration_seconds: float = 0.0, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("recording.requested", source, metadata or {}); self.duration_seconds = duration_seconds; self.mode = "timed" if duration_seconds > 0 else "vad"
@dataclass(slots=True)
class RecordingStarted(RuntimeEvent):
    def __init__(self, *, source: str = "recorder", metadata: dict[str, Any] | None = None): super().__init__("recording.started", source, metadata or {})
@dataclass(slots=True)
class RecordingCompleted(RuntimeEvent):
    wav_path: str | None = None; sample_rate: int = 0
    def __init__(self, wav_path: str | None = None, sample_rate: int = 0, *, source: str = "recorder", metadata: dict[str, Any] | None = None): super().__init__("recording.completed", source, metadata or {}); self.wav_path = wav_path; self.sample_rate = sample_rate
@dataclass(slots=True)
class RecordingFailed(RuntimeEvent):
    error: str = ""
    def __init__(self, error: str, *, source: str = "recorder", metadata: dict[str, Any] | None = None): super().__init__("recording.failed", source, metadata or {}); self.error = error

# ASR/text events
@dataclass(slots=True)
class ASRRequested(RuntimeEvent):
    audio_path: str | None = None
    def __init__(self, audio_path: str | None = None, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("asr.requested", source, metadata or {}); self.audio_path = audio_path
@dataclass(slots=True)
class ASRCompleted(RuntimeEvent):
    audio_path: str | None = None; text: str = ""; raw_text: str | None = None; language: str | None = None; asr_metadata: dict[str, Any] = field(default_factory=dict)
    def __init__(self, audio_path: str | None = None, text: str = "", raw_text: str | None = None, language: str | None = None, asr_metadata: dict[str, Any] | None = None, *, source: str = "stt", metadata: dict[str, Any] | None = None, **kwargs: Any):
        if "metadata" in kwargs and asr_metadata is None:
            asr_metadata = kwargs.pop("metadata")
        if asr_metadata is None and metadata is not None and source == "stt":
            asr_metadata, metadata = metadata, None
        super().__init__("asr.completed", source, metadata or {}); self.audio_path = audio_path; self.text = text; self.raw_text = raw_text; self.language = language; self.asr_metadata = asr_metadata or {}
@dataclass(slots=True)
class ASRFailed(RuntimeEvent):
    error: str = ""; audio_path: str | None = None
    def __init__(self, error: str, audio_path: str | None = None, *, source: str = "stt", metadata: dict[str, Any] | None = None): super().__init__("asr.failed", source, metadata or {}); self.error = error; self.audio_path = audio_path
@dataclass(slots=True)
class ASRTextCorrected(RuntimeEvent):
    original_text: str = ""; corrected_text: str = ""
    def __init__(self, original_text: str, corrected_text: str, *, source: str = "asr_postprocessor", metadata: dict[str, Any] | None = None): super().__init__("asr.text.corrected", source, metadata or {}); self.original_text = original_text; self.corrected_text = corrected_text
@dataclass(slots=True)
class UserUtteranceReady(RuntimeEvent):
    text: str = ""
    def __init__(self, text: str, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("user.utterance.ready", source, metadata or {}); self.text = text

# Task events
@dataclass(slots=True)
class IntentDetected(RuntimeEvent):
    intent: str = ""; confidence: float = 0.0
    def __init__(self, intent: str, confidence: float = 1.0, *, source: str = "router", metadata: dict[str, Any] | None = None): super().__init__("intent.detected", source, metadata or {}); self.intent = intent; self.confidence = confidence
@dataclass(slots=True)
class TaskPlanCreated(RuntimeEvent):
    plan: dict[str, Any] = field(default_factory=dict)
    def __init__(self, plan: dict[str, Any], *, source: str = "planner", metadata: dict[str, Any] | None = None): super().__init__("task.plan.created", source, metadata or {}); self.plan = plan
@dataclass(slots=True)
class ToolExecutionRequested(RuntimeEvent):
    tool_name: str = "openclaw"; parameters: dict[str, Any] = field(default_factory=dict); text: str = ""
    def __init__(self, tool_name: str = "openclaw", parameters: dict[str, Any] | None = None, text: str = "", *, source: str = "router", metadata: dict[str, Any] | None = None): super().__init__("tool.execution.requested", source, metadata or {}); self.tool_name = tool_name; self.parameters = parameters or {}; self.text = text or str(self.parameters.get("command") or self.parameters.get("text") or "")
@dataclass(slots=True)
class ToolExecutionStarted(RuntimeEvent):
    tool_name: str = ""; request_id: str = ""
    def __init__(self, tool_name: str, request_id: str = "", *, source: str = "executor", metadata: dict[str, Any] | None = None): super().__init__("tool.execution.started", source, metadata or {}); self.tool_name = tool_name; self.request_id = request_id
@dataclass(slots=True)
class ToolExecutionCompleted(RuntimeEvent):
    tool_name: str = ""; result: dict[str, Any] = field(default_factory=dict)
    def __init__(self, tool_name: str, result: dict[str, Any], *, source: str = "executor", metadata: dict[str, Any] | None = None): super().__init__("tool.execution.completed", source, metadata or {}); self.tool_name = tool_name; self.result = result
@dataclass(slots=True)
class ToolExecutionFailed(RuntimeEvent):
    tool_name: str = ""; error: str = ""; result: dict[str, Any] = field(default_factory=dict)
    def __init__(self, tool_name: str, error: str, result: dict[str, Any] | None = None, *, source: str = "executor", metadata: dict[str, Any] | None = None): super().__init__("tool.execution.failed", source, metadata or {}); self.tool_name = tool_name; self.error = error; self.result = result or {}

# Feedback events
@dataclass(slots=True)
class TTSRequested(RuntimeEvent):
    text: str = ""; output_path: str | None = None; voice: str | None = None; speaker: str | None = None; prompt_wav: str | None = None; prompt_text: str | None = None
    def __init__(self, text: str, output_path: str | None = None, voice: str | None = None, speaker: str | None = None, prompt_wav: str | None = None, prompt_text: str | None = None, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("tts.requested", source, metadata or {}); self.text=text; self.output_path=output_path; self.voice=voice; self.speaker=speaker; self.prompt_wav=prompt_wav; self.prompt_text=prompt_text
@dataclass(slots=True)
class TTSStarted(RuntimeEvent):
    text: str = ""
    def __init__(self, text: str, *, source: str = "tts", metadata: dict[str, Any] | None = None): super().__init__("tts.started", source, metadata or {}); self.text = text
@dataclass(slots=True)
class TTSCompleted(RuntimeEvent):
    text: str = ""; audio_path: str | None = None; sample_rate: int | None = None; tts_metadata: dict[str, Any] = field(default_factory=dict)
    def __init__(self, text: str, audio_path: str | None = None, sample_rate: int | None = None, tts_metadata: dict[str, Any] | None = None, *, source: str = "tts", metadata: dict[str, Any] | None = None, **kwargs: Any):
        if "metadata" in kwargs and tts_metadata is None:
            tts_metadata = kwargs.pop("metadata")
        if tts_metadata is None and metadata is not None and source == "tts":
            tts_metadata, metadata = metadata, None
        super().__init__("tts.completed", source, metadata or {}); self.text=text; self.audio_path=audio_path; self.sample_rate=sample_rate; self.tts_metadata=tts_metadata or {}
@dataclass(slots=True)
class UIMessageRequested(RuntimeEvent):
    message: str = ""; level: str = "info"
    def __init__(self, message: str, level: str = "info", *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("ui.message.requested", source, metadata or {}); self.message=message; self.level=level
@dataclass(slots=True)
class StatusChanged(RuntimeEvent):
    state: str = ""; step: str | None = None
    def __init__(self, state: str, step: str | None = None, *, source: str = "context", metadata: dict[str, Any] | None = None): super().__init__("status.changed", source, metadata or {}); self.state=state; self.step=step

# Control/manual events
@dataclass(slots=True)
class PauseWakeWordRequested(RuntimeEvent):
    def __init__(self, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("wakeword.pause.requested", source, metadata or {})
@dataclass(slots=True)
class ResumeWakeWordRequested(RuntimeEvent):
    def __init__(self, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("wakeword.resume.requested", source, metadata or {})
@dataclass(slots=True)
class CancelCurrentTaskRequested(RuntimeEvent):
    reason: str = "manual_cancel"
    def __init__(self, reason: str = "manual_cancel", *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("task.cancel.requested", source, metadata or {}); self.reason=reason
@dataclass(slots=True)
class UserConfirmationRequired(RuntimeEvent):
    prompt: str = ""; request: dict[str, Any] = field(default_factory=dict)
    def __init__(self, prompt: str, request: dict[str, Any] | None = None, *, source: str = "executor", metadata: dict[str, Any] | None = None): super().__init__("user.confirmation.required", source, metadata or {}); self.prompt=prompt; self.request=request or {}
@dataclass(slots=True)
class UserConfirmationReceived(RuntimeEvent):
    confirmed: bool = False; request_id: str | None = None
    def __init__(self, confirmed: bool, request_id: str | None = None, *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("user.confirmation.received", source, metadata or {}); self.confirmed=confirmed; self.request_id=request_id
@dataclass(slots=True)
class ErrorOccurred(RuntimeEvent):
    error: str = ""; exception_type: str | None = None; original_event_id: str | None = None
    def __init__(self, error: str, exception_type: str | None = None, original_event_id: str | None = None, *, source: str = "runtime", metadata: dict[str, Any] | None = None): super().__init__("error.occurred", source, metadata or {}); self.error=error; self.exception_type=exception_type; self.original_event_id=original_event_id
@dataclass(slots=True)
class ManualOverrideRequested(RuntimeEvent):
    target_event_type: str = ""; replacement_payload: dict[str, Any] = field(default_factory=dict); target_event_id: str | None = None; reason: str = ""
    def __init__(self, target_event_type: str, replacement_payload: dict[str, Any], target_event_id: str | None = None, reason: str = "", *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("manual.override.requested", source, metadata or {}); self.target_event_type=target_event_type; self.target_event_id=target_event_id; self.replacement_payload=replacement_payload; self.reason=reason
@dataclass(slots=True)
class ManualOverrideApplied(RuntimeEvent):
    target_event_type: str = ""; replacement_payload: dict[str, Any] = field(default_factory=dict); target_event_id: str | None = None
    def __init__(self, target_event_type: str, replacement_payload: dict[str, Any], target_event_id: str | None = None, *, source: str = "orchestrator", metadata: dict[str, Any] | None = None): super().__init__("manual.override.applied", source, metadata or {}); self.target_event_type=target_event_type; self.target_event_id=target_event_id; self.replacement_payload=replacement_payload
@dataclass(slots=True)
class StepRetryRequested(RuntimeEvent):
    step_name: str = ""
    def __init__(self, step_name: str, *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("step.retry.requested", source, metadata or {}); self.step_name=step_name
@dataclass(slots=True)
class StepSkipped(RuntimeEvent):
    step_name: str = ""; reason: str = ""
    def __init__(self, step_name: str, reason: str = "manual_skip", *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("step.skipped", source, metadata or {}); self.step_name=step_name; self.reason=reason
@dataclass(slots=True)
class RuntimeJumpRequested(RuntimeEvent):
    target_state: str = "idle"; optional_event_payload: dict[str, Any] = field(default_factory=dict); reason: str = ""
    def __init__(self, target_state: str, optional_event_payload: dict[str, Any] | None = None, reason: str = "manual_jump", *, source: str = "console", metadata: dict[str, Any] | None = None): super().__init__("runtime.jump.requested", source, metadata or {}); self.target_state=target_state; self.optional_event_payload=optional_event_payload or {}; self.reason=reason


def __getattr__(name: str):
    """Compatibility for older imports: from sylphos.runtime.events import EventBus."""
    if name in {"EventBus", "EventHandler"}:
        from sylphos.runtime.event_bus import EventBus, EventHandler
        return {"EventBus": EventBus, "EventHandler": EventHandler}[name]
    raise AttributeError(name)
