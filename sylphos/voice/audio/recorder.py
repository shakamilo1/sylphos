from __future__ import annotations

import logging
from pathlib import Path

from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import RecordingCompleted, RecordingFailed, RecordingRequested, RecordingStarted


class RecorderService:
    """Event adapter for existing CommandRecorder; dummy-completes when no AudioHub is attached."""
    def __init__(self, event_bus: EventBus, *, audio_hub=None, samplerate: int = 44100, output_dir: str = "outputs/recordings", dummy_when_no_audio: bool = True) -> None:
        self.event_bus = event_bus; self.audio_hub = audio_hub; self.samplerate = samplerate; self.output_dir = output_dir; self.dummy_when_no_audio = dummy_when_no_audio
        self.logger = logging.getLogger(self.__class__.__name__)
        self._recorder = None
    def start(self): self.event_bus.subscribe("recording.requested", self._on_recording_requested)
    def stop(self): self.event_bus.unsubscribe("recording.requested", self._on_recording_requested)
    def _ensure_recorder(self):
        if self._recorder is None:
            from voice.audio.recorder import CommandRecorder
            self._recorder = CommandRecorder(sample_rate=self.samplerate, output_dir=Path(self.output_dir), on_record_complete=self._on_complete)
            if self.audio_hub is not None and getattr(self.audio_hub, "_hub", None) is not None:
                self.audio_hub.subscribe(self._recorder.consume)
        return self._recorder
    def _on_recording_requested(self, event):
        self.event_bus.publish(RecordingStarted())
        try:
            if self.audio_hub is None or (hasattr(self.audio_hub, "enabled") and not self.audio_hub.enabled):
                self.logger.info("No live audio hub; publishing dummy RecordingCompleted for runtime flow")
                self.event_bus.publish(RecordingCompleted(wav_path=None, sample_rate=self.samplerate))
                return
            recorder = self._ensure_recorder()
            duration = float(getattr(event, "duration_seconds", 0.0) or 0.0)
            recorder.start_recording(duration_seconds=duration)
        except Exception as exc:
            self.logger.exception("RecorderService failed")
            self.event_bus.publish(RecordingFailed(str(exc)))
    def _on_complete(self, wav_path, sample_rate):
        self.event_bus.publish(RecordingCompleted(str(wav_path) if wav_path else None, int(sample_rate or self.samplerate)))
    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("Recorder cancel requested")
    def close(self):
        self.stop()
        if self._recorder is not None and hasattr(self._recorder, "close"):
            self._recorder.close()
