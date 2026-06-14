from __future__ import annotations

import logging
import importlib.resources as ir
from pathlib import Path

from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import PauseWakeWordRequested, ResumeWakeWordRequested, WakeWordDetected, WakeWordScoreUpdated


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class OpenWakeWordEngineAdapter:
    """Adapter wrapping existing voice.wakeword engine without changing detection logic."""
    def __init__(
        self,
        event_bus: EventBus,
        *,
        audio_hub=None,
        enabled: bool = False,
        console_wake_score_display: str = "status",
        wakeword_score_log_interval_seconds: float = 1.0,
        **kwargs,
    ) -> None:
        self.event_bus = event_bus; self.audio_hub = audio_hub; self.enabled = enabled; self.kwargs = kwargs
        self.console_wake_score_display = console_wake_score_display
        self.wakeword_score_log_interval_seconds = wakeword_score_log_interval_seconds
        self.logger = logging.getLogger(self.__class__.__name__)
        self._engine = None
    def _ensure_engine(self):
        if self._engine is None:
            self._validate_model_config()
            from voice.wakeword.openwakeword_engine import OpenWakeWordEngine
            self._engine = OpenWakeWordEngine(
                **self.kwargs,
                score_log_interval_seconds=self.wakeword_score_log_interval_seconds,
                log_scores_to_info=self.console_wake_score_display == "log",
            )
            self._engine.set_callback(lambda name, score: self.event_bus.publish(WakeWordDetected(name=name, score=score)))
            if self.console_wake_score_display == "status":
                self._engine.set_score_callback(
                    lambda name, score: self.event_bus.publish(WakeWordScoreUpdated(name=name, score=score))
                )
            if self.audio_hub is not None:
                self.audio_hub.subscribe(self._engine.consume)
        return self._engine

    def _validate_model_config(self) -> None:
        source = self.kwargs.get("wakeword_model_source", "openwakeword_resource")
        model_name = self.kwargs.get("wakeword_model_name")
        relative_path = self.kwargs.get("wakeword_model_relative_path")
        if not model_name and not relative_path:
            raise RuntimeError(
                "AUDIO_ENABLED=True requires an explicit wakeword model. Configure "
                "WAKEWORD_MODEL_PATH, WAKEWORD_MODEL_RELATIVE_PATH, or WAKEWORD_MODEL_NAME "
                "in config/local_config.py. Refusing to load the openWakeWord default model "
                "implicitly."
            )

        attempted_path = None
        if source == "openwakeword_resource" and model_name:
            attempted_path = Path(str(ir.files("openwakeword") / "resources" / "models")) / str(model_name)
        elif source == "project_relative" and relative_path:
            attempted_path = Path(str(relative_path))
            if not attempted_path.is_absolute():
                attempted_path = PROJECT_ROOT / attempted_path

        if attempted_path is not None and not attempted_path.exists():
            raise RuntimeError(
                f"Configured wakeword model file does not exist: {attempted_path}. "
                "Check WAKEWORD_MODEL_PATH, WAKEWORD_MODEL_RELATIVE_PATH, "
                "WAKEWORD_MODEL_DIR, WAKEWORD_MODEL_NAME, and WAKEWORD_MODEL_SOURCE."
            )
    def start(self):
        self.event_bus.subscribe("wakeword.pause.requested", self._on_pause)
        self.event_bus.subscribe("wakeword.resume.requested", self._on_resume)
        if self.enabled:
            self._ensure_engine()
        else:
            self.logger.info("WakeWord engine disabled by config; use console 'w' to simulate")
    def _on_pause(self, event): self.pause()
    def _on_resume(self, event): self.resume()
    def pause(self):
        if self._engine: self._engine.pause()
        self.logger.info("Wakeword paused")
    def resume(self):
        if self._engine:
            if hasattr(self._engine, "reset"): self._engine.reset()
            self._engine.resume()
        self.logger.info("Wakeword resumed")
    def stop(self):
        self.event_bus.unsubscribe("wakeword.pause.requested", self._on_pause)
        self.event_bus.unsubscribe("wakeword.resume.requested", self._on_resume)
    def cancel(self): pass
    def close(self): self.stop()
