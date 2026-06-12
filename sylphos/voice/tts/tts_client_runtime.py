from __future__ import annotations

import logging
from typing import Any


class TTSClientRuntimeAdapter:
    """Runtime TTS adapter that reuses Sylphos' validated ``TTSClient``.

    This is the Windows-friendly runtime path for ``TTS_PROVIDER=base`` or
    ``TTS_PROVIDER=tts_client``.  It deliberately imports ``TTSClient`` lazily
    from ``sylphos.voice.tts`` so selecting this provider never touches the
    source-installed CosyVoice engine path (``cosyvoice.cli.cosyvoice``).
    """

    def __init__(
        self,
        model_version: str = "base",
        timeout_seconds: int = 240,
        auto_play: bool = True,
        voice_id: str = "official",
        **kwargs: Any,
    ) -> None:
        self.model_version = model_version
        self.timeout_seconds = int(timeout_seconds)
        self.auto_play = bool(auto_play)
        self.voice_id = voice_id
        self.extra_options = dict(kwargs)
        self._client = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def _ensure_client(self):
        if self._client is None:
            from sylphos.voice.tts import TTSClient

            self._client = TTSClient(
                model_version=self.model_version,
                timeout_seconds=self.timeout_seconds,
                auto_play=self.auto_play,
            )
        return self._client

    def speak(self, text: str) -> None:
        audio_path = self._ensure_client().speak(text, voice_id=self.voice_id)
        if audio_path is None:
            raise RuntimeError("TTSClient failed to synthesize speech")
        self.logger.info("TTSClient synthesized and played: %s", audio_path)

    def start(self) -> None:
        self.logger.debug("TTSClientRuntimeAdapter ready")

    def stop(self) -> None:
        self.logger.debug("TTSClientRuntimeAdapter stopped")

    def pause(self) -> None:
        self.logger.debug("TTSClientRuntimeAdapter pause requested")

    def resume(self) -> None:
        self.logger.debug("TTSClientRuntimeAdapter resume requested")

    def cancel(self) -> None:
        # TTSClient.speak is currently synchronous; there is no in-flight
        # cancellation hook to call yet.  Keep the method for Runtime parity.
        self.logger.debug("TTSClientRuntimeAdapter cancel requested")

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._client = None
