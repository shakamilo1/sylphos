from __future__ import annotations

import json
import logging
from typing import Any

from sylphos.runtime.context import RuntimeContext
from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import (
    ASRCompleted, ASRFailed, ASRRequested, ASRTextCorrected, CancelCurrentTaskRequested, ErrorOccurred,
    ManualOverrideApplied, ManualOverrideRequested, PauseWakeWordRequested, RecordingCompleted, RecordingRequested,
    ResumeWakeWordRequested, RuntimeEvent, RuntimeJumpRequested, StatusChanged, StepRetryRequested, StepSkipped,
    TTSRequested, TextInputReceived, ToolExecutionCompleted, ToolExecutionFailed, ToolExecutionRequested,
    ToolExecutionStarted, UIMessageRequested, UserUtteranceReady, WakeWordDetected,
)
from sylphos.runtime.state import RuntimeState


class SimpleRouter:
    def __init__(self, default_tool: str = "dummy") -> None:
        self.default_tool = default_tool or "dummy"

    def route(self, text: str) -> ToolExecutionRequested:
        command = text.strip()
        simple = ("打开浏览器", "打开记事本", "查看当前目录")
        if command in simple or command.startswith("打开") or command.startswith("查看"):
            return ToolExecutionRequested(self.default_tool, {"command": command}, text=command)
        plan = {"type": "dummy_llm_plan", "command": command}
        return ToolExecutionRequested(self.default_tool, {"command": command, "plan": plan}, text=command, source="dummy_planner")


class RuntimeOrchestrator:
    """Event-driven policy layer. Modules publish/subscribe independently; this class only coordinates the default loop."""

    def __init__(self, *, event_bus: EventBus, context: RuntimeContext, registry, config, post_processors: list[Any] | None = None, router: SimpleRouter | None = None) -> None:
        self.event_bus = event_bus; self.context = context; self.registry = registry; self.config = config
        self.post_processors = post_processors or []; self.router = router or SimpleRouter()
        self.logger = logging.getLogger(self.__class__.__name__)
        self._handling_error = False

    def start(self):
        subscriptions = {
            "wakeword.detected": self._on_wakeword_detected,
            "recording.completed": self._on_recording_completed,
            "recording.failed": self._on_recording_failed,
            "asr.completed": self._on_asr_completed,
            "asr.failed": self._on_asr_failed,
            "text.input.received": self._on_text_input,
            "user.utterance.ready": self._on_user_utterance_ready,
            "tool.execution.requested": self._on_tool_execution_requested,
            "tool.execution.completed": self._on_tool_execution_completed,
            "tool.execution.failed": self._on_tool_execution_failed,
            "task.cancel.requested": self._on_cancel,
            "runtime.jump.requested": self._on_jump,
            "manual.override.requested": self._on_manual_override,
            "step.retry.requested": self._on_step_retry,
            "step.skipped": self._on_step_skipped,
            "error.occurred": self._on_error,
        }
        self._subscriptions = subscriptions
        for event_type, handler in subscriptions.items(): self.event_bus.subscribe(event_type, handler)
        self._set_state(RuntimeState.WAKEWORD_LISTENING, "startup")
        self.event_bus.publish(ResumeWakeWordRequested(source="orchestrator"))
        self.event_bus.publish(UIMessageRequested("Sylphos Runtime 已启动，等待事件。"))

    def stop(self):
        for event_type, handler in getattr(self, "_subscriptions", {}).items(): self.event_bus.unsubscribe(event_type, handler)

    def _set_state(self, state: RuntimeState | str, step: str | None = None):
        self.context.set_state(state, step)
        self.event_bus.publish(StatusChanged(str(self.context.state), step))

    def _mark(self, event: RuntimeEvent, step: str): self.context.mark_event(event, step)

    def _on_wakeword_detected(self, event):
        self._mark(event, "wakeword_detected")
        self._set_state(RuntimeState.LISTENING, "wakeword_detected")
        self.event_bus.publish(UIMessageRequested("检测到唤醒词"))
        self.event_bus.publish(TTSRequested(getattr(self.config, "TTS_ON_WAKE", "我在听")))
        self.event_bus.publish(PauseWakeWordRequested())
        self._set_state(RuntimeState.RECORDING, "recording")
        self.event_bus.publish(RecordingRequested(float(getattr(self.config, "RECORD_SECONDS", 0.0) or 0.0)))

    def _on_recording_completed(self, event):
        self._mark(event, "recording_completed")
        self.context.last_audio_path = getattr(event, "wav_path", None)
        self._set_state(RuntimeState.TRANSCRIBING, "transcribing")
        self.event_bus.publish(ASRRequested(self.context.last_audio_path))

    def _on_recording_failed(self, event):
        self.event_bus.publish(ErrorOccurred(getattr(event, "error", "recording failed"), original_event_id=event.event_id))

    def _on_asr_completed(self, event):
        self._mark(event, "asr_completed")
        original = getattr(event, "text", "")
        text = original
        self.context.last_asr_text = text
        for processor in self.post_processors:
            text = processor.process(text, self.context)
        if text != original:
            self.event_bus.publish(ASRTextCorrected(original, text))
        self.event_bus.publish(UserUtteranceReady(text, source="asr_postprocessor"))

    def _on_asr_failed(self, event):
        self.event_bus.publish(ErrorOccurred(getattr(event, "error", "asr failed"), original_event_id=event.event_id))

    def _on_text_input(self, event):
        self._mark(event, "text_input")
        self.event_bus.publish(UserUtteranceReady(getattr(event, "text", ""), source=event.source))

    def _on_user_utterance_ready(self, event):
        self._mark(event, "user_utterance_ready")
        text = getattr(event, "text", "").strip()
        self.context.last_user_utterance = text
        self._set_state(RuntimeState.THINKING, "routing")
        self.event_bus.publish(UIMessageRequested(f"用户指令：{text}"))
        request = self.router.route(text)
        self.event_bus.publish(request)

    def _on_tool_execution_requested(self, event):
        self._mark(event, "tool_execution_requested")
        self.context.last_tool_request = event.payload
        self._set_state(RuntimeState.EXECUTING, "executing")
        self.event_bus.publish(TTSRequested(getattr(self.config, "TTS_ON_EXECUTING", "正在处理")))
        tool_name = getattr(event, "tool_name", "openclaw") or getattr(self.config, "TOOL_EXECUTOR_PROVIDER", "dummy")
        executor = self.registry.get_executor(tool_name) or self.registry.get_executor(getattr(self.config, "TOOL_EXECUTOR_PROVIDER", "dummy")) or self.registry.get_executor("dummy")
        if executor is None:
            self.event_bus.publish(ToolExecutionFailed(tool_name, f"executor not registered: {tool_name}")); return
        self.event_bus.publish(ToolExecutionStarted(tool_name, event.event_id))
        try:
            result = executor.execute(event, self.context)
            self.event_bus.publish(ToolExecutionCompleted(tool_name, result))
        except Exception as exc:
            if hasattr(exc, "result"):
                self.logger.error("Tool execution failed: %s", exc)
            else:
                self.logger.exception("Tool execution failed")
            self.event_bus.publish(ToolExecutionFailed(tool_name, str(exc), result=getattr(exc, "result", {})))

    def _on_tool_execution_completed(self, event):
        self._mark(event, "tool_execution_completed")
        result = getattr(event, "result", {})
        self.context.last_tool_result = result
        raw_response = result.get("raw_response", result)
        assistant_text = result.get("assistant_text") or result.get("text")
        speak_text = result.get("speak_text") or assistant_text or result.get("summary") or result.get("stdout") or "任务完成"
        display_text = result.get("display_text") or result.get("ui_text") or assistant_text or json.dumps(result, ensure_ascii=False)
        self.logger.info("OpenClaw raw_response=%s", raw_response)
        self.logger.info("OpenClaw assistant_text=%s", assistant_text)
        self.logger.info("OpenClaw speak_text=%s", speak_text)
        self._set_state(RuntimeState.SPEAKING, "speaking")
        self.event_bus.publish(UIMessageRequested(f"执行结果：{display_text}"))
        self.event_bus.publish(TTSRequested(str(speak_text)[:120]))
        self._set_state(RuntimeState.WAKEWORD_LISTENING, "wakeword_listening")
        self.event_bus.publish(ResumeWakeWordRequested())

    def _on_tool_execution_failed(self, event):
        result = getattr(event, "result", {}) or {}
        raw_response = result.get("raw_response", result)
        assistant_text = result.get("assistant_text")
        error_message = result.get("error_message") or result.get("error") or getattr(event, "error", "tool failed")
        speak_text = result.get("speak_text") or f"OpenClaw 执行失败：{error_message}"
        self.logger.info("OpenClaw raw_response=%s", raw_response)
        self.logger.info("OpenClaw assistant_text=%s", assistant_text)
        self.logger.info("OpenClaw speak_text=%s", speak_text)
        self.event_bus.publish(UIMessageRequested(f"错误：{error_message}", level="error"))
        self.event_bus.publish(TTSRequested(str(speak_text)[:120]))
        self.event_bus.publish(ErrorOccurred(str(error_message), original_event_id=event.event_id, source="tts"))
        self._set_state(RuntimeState.WAKEWORD_LISTENING, "wakeword_listening")
        self.event_bus.publish(ResumeWakeWordRequested())

    def _on_error(self, event):
        if self._handling_error: return
        self._handling_error = True
        try:
            self._set_state(RuntimeState.ERROR, "error")
            self.event_bus.publish(UIMessageRequested(f"错误：{getattr(event, 'error', '')}", level="error"))
            if getattr(event, "source", "") != "tts":
                self.event_bus.publish(TTSRequested(getattr(self.config, "TTS_ON_FAILED", "执行失败，请查看文本结果")))
            self._set_state(RuntimeState.WAKEWORD_LISTENING, "wakeword_listening")
            self.event_bus.publish(ResumeWakeWordRequested())
        finally:
            self._handling_error = False

    def _on_cancel(self, event):
        self.context.interrupted_by_manual_override = True
        for module in list(self.registry.modules.values()) + list(self.registry.executors.values()):
            cancel = getattr(module, "cancel", None)
            if callable(cancel):
                try: cancel()
                except Exception: self.logger.exception("cancel failed module=%r", module)
        self.context.reset_task()
        self._set_state(RuntimeState.WAKEWORD_LISTENING, "cancelled")
        self.event_bus.publish(UIMessageRequested(f"已取消当前任务：{getattr(event, 'reason', '')}"))
        self.event_bus.publish(ResumeWakeWordRequested())

    def _on_jump(self, event):
        try: self._set_state(RuntimeState.coerce(getattr(event, "target_state", "idle")), "manual_jump")
        except ValueError: self.event_bus.publish(ErrorOccurred(f"未知状态：{getattr(event, 'target_state', '')}")); return
        self.event_bus.publish(UIMessageRequested(f"已跳转到状态：{self.context.state}"))
        payload = getattr(event, "optional_event_payload", {}) or {}
        et = payload.get("event_type")
        if et == "user.utterance.ready": self.event_bus.publish(UserUtteranceReady(payload.get("text", ""), source="runtime_jump"))
        elif et == "asr.completed": self.event_bus.publish(ASRCompleted(text=payload.get("text", ""), source="runtime_jump"))
        elif et == "tool.execution.requested": self.event_bus.publish(ToolExecutionRequested(payload.get("tool_name", "openclaw"), payload.get("parameters", {}), source="runtime_jump"))
        if self.context.state == RuntimeState.WAKEWORD_LISTENING: self.event_bus.publish(ResumeWakeWordRequested())

    def _on_manual_override(self, event):
        self.context.interrupted_by_manual_override = True
        payload = getattr(event, "replacement_payload", {})
        target = getattr(event, "target_event_type", "")
        self.event_bus.publish(ManualOverrideApplied(target, payload, getattr(event, "target_event_id", None)))
        if target == "asr.completed": self.event_bus.publish(ASRCompleted(text=payload.get("text", ""), source="manual_override"))
        elif target == "user.utterance.ready": self.event_bus.publish(UserUtteranceReady(payload.get("text", ""), source="manual_override"))
        elif target == "tool.execution.requested": self.event_bus.publish(ToolExecutionRequested(payload.get("tool_name", "openclaw"), payload.get("parameters", {}), source="manual_override"))
        elif target == "tts.requested": self.event_bus.publish(TTSRequested(payload.get("text", ""), source="manual_override"))

    def _on_step_retry(self, event):
        step = getattr(event, "step_name", "")
        self.event_bus.publish(UIMessageRequested(f"请求重试步骤：{step}"))
        if step in {"asr", "transcribing"}: self.event_bus.publish(ASRRequested(self.context.last_audio_path))
        elif step in {"utterance", "routing"} and self.context.last_user_utterance: self.event_bus.publish(UserUtteranceReady(self.context.last_user_utterance, source="retry"))
        elif step in {"tool", "execution"} and self.context.last_tool_request: self.event_bus.publish(ToolExecutionRequested(parameters=self.context.last_tool_request, source="retry"))

    def _on_step_skipped(self, event):
        self.event_bus.publish(UIMessageRequested(f"已跳过步骤：{getattr(event, 'step_name', '')}"))
        self._set_state(RuntimeState.WAKEWORD_LISTENING, "step_skipped")
        self.event_bus.publish(ResumeWakeWordRequested())
