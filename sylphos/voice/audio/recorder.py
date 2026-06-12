from __future__ import annotations

import logging

from sylphos.runtime.event_bus import EventBus
from sylphos.runtime.events import RecordingCompleted, RecordingFailed, RecordingRequested, RecordingStarted


class RecorderService:
    """Event adapter for existing CommandRecorder; dummy-completes when no AudioHub is attached."""

    def __init__(
        self,
        event_bus: EventBus,
        *,
        audio_hub=None,
        samplerate: int = 44100,
        output_dir: str = "outputs/recordings",
        dummy_when_no_audio: bool = True,
        channels: int = 1,
        sample_width_bytes: int = 2,
        save_mode: str = "latest",
        latest_filename: str = "latest_command.wav",
        vad_enabled: bool = True,
        vad_sample_rate: int = 16000,
        vad_threshold: float = 0.5,
        vad_min_speech_duration_ms: int = 150,
        vad_min_silence_duration_ms: int = 300,
        vad_speech_pad_ms: int = 100,
        vad_end_silence_ms: int = 800,
        vad_prebuffer_ms: int = 300,
        vad_check_interval_ms: int = 200,
    ) -> None:
        self.event_bus = event_bus
        self.audio_hub = audio_hub
        self.samplerate = samplerate
        self.output_dir = output_dir
        self.dummy_when_no_audio = dummy_when_no_audio
        self.channels = channels
        self.sample_width_bytes = sample_width_bytes
        self.save_mode = save_mode
        self.latest_filename = latest_filename
        self.vad_enabled = vad_enabled
        self.vad_sample_rate = vad_sample_rate
        self.vad_threshold = vad_threshold
        self.vad_min_speech_duration_ms = vad_min_speech_duration_ms
        self.vad_min_silence_duration_ms = vad_min_silence_duration_ms
        self.vad_speech_pad_ms = vad_speech_pad_ms
        self.vad_end_silence_ms = vad_end_silence_ms
        self.vad_prebuffer_ms = vad_prebuffer_ms
        self.vad_check_interval_ms = vad_check_interval_ms
        self.logger = logging.getLogger(self.__class__.__name__)
        self._recorder = None

    def start(self): self.event_bus.subscribe("recording.requested", self._on_recording_requested)
    def stop(self): self.event_bus.unsubscribe("recording.requested", self._on_recording_requested)

    def _ensure_recorder(self):
        if self._recorder is None:
            from voice.audio.recorder import CommandRecorder
            self._recorder = CommandRecorder(
                input_rate=self.samplerate,
                save_dir=str(self.output_dir),
                channels=self.channels,
                sample_width_bytes=self.sample_width_bytes,
                on_record_complete=self._on_complete,
                save_mode=self.save_mode,
                latest_filename=self.latest_filename,
                vad_enabled=self.vad_enabled,
                vad_sample_rate=self.vad_sample_rate,
                vad_threshold=self.vad_threshold,
                vad_min_speech_duration_ms=self.vad_min_speech_duration_ms,
                vad_min_silence_duration_ms=self.vad_min_silence_duration_ms,
                vad_speech_pad_ms=self.vad_speech_pad_ms,
                vad_end_silence_ms=self.vad_end_silence_ms,
                vad_prebuffer_ms=self.vad_prebuffer_ms,
                vad_check_interval_ms=self.vad_check_interval_ms,
            )
            if self.audio_hub is not None and hasattr(self.audio_hub, "subscribe"):
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

    def _on_complete(self, wav_path, audio_i16=None, sample_rate=None):
        # Existing CommandRecorder calls (wav_path, audio_i16, sample_rate).  Keep
        # accepting the older two-argument adapter shape for compatibility.
        if sample_rate is None and isinstance(audio_i16, int):
            sample_rate = audio_i16
        self.event_bus.publish(RecordingCompleted(str(wav_path) if wav_path else None, int(sample_rate or self.samplerate)))

    def pause(self): pass
    def resume(self): pass
    def cancel(self): self.logger.info("Recorder cancel requested")
    def close(self):
        self.stop()
        if self._recorder is not None and hasattr(self._recorder, "close"):
            self._recorder.close()
