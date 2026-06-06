from __future__ import annotations

"""Windows-side client for a CosyVoice3 FastAPI TTS service running in WSL2."""

import base64
import json
import mimetypes
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, parse, request

_DEFAULT_TTS_URL = "http://127.0.0.1:9880/v1/tts"
_VALID_MODEL_VERSIONS = {"base", "rl"}


class TTSClient:
    """Call a WSL2 CosyVoice3 FastAPI endpoint, save the WAV, and play it."""

    def __init__(
        self,
        api_url: str = _DEFAULT_TTS_URL,
        model_version: str = "base",
        timeout_seconds: float = 60.0,
        temp_dir: str | Path | None = None,
        auto_play: bool = True,
    ) -> None:
        self.api_url = api_url
        self.model_version = self._normalize_model_version(model_version)
        self.timeout_seconds = timeout_seconds
        self.temp_dir = Path(temp_dir) if temp_dir is not None else Path(tempfile.gettempdir()) / "sylphos_tts"
        self.auto_play = auto_play

    def speak(self, text: str, model_version: str | None = None, **extra_payload: Any) -> Path | None:
        """Synthesize text to a temporary WAV file and play it with the default player."""
        try:
            wav_path = self.synthesize_to_temp_file(text, model_version=model_version, **extra_payload)
            if self.auto_play:
                self.play(wav_path)
            return wav_path
        except Exception as exc:
            print(f"[Sylphos TTS] {exc}", file=sys.stderr)
            return None

    def synthesize_to_temp_file(self, text: str, model_version: str | None = None, **extra_payload: Any) -> Path:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.temp_dir / f"sylphos_tts_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.wav"
        return self.synthesize_to_file(text, output_path, model_version=model_version, **extra_payload)

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path,
        model_version: str | None = None,
        **extra_payload: Any,
    ) -> Path:
        """Call /v1/tts and save the returned WAV bytes to output_path."""
        clean_text = text.strip() if text else ""
        if not clean_text:
            raise ValueError("TTS text must not be empty.")

        version = self._normalize_model_version(model_version or self.model_version)
        payload: dict[str, Any] = {
            "text": clean_text,
            "model_version": version,
        }
        payload.update(extra_payload)

        response_body, content_type = self._post_json(payload)
        wav_bytes = self._extract_wav_bytes(response_body, content_type)
        if not wav_bytes:
            raise RuntimeError("CosyVoice3 API returned an empty audio body.")

        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(wav_bytes)
        return output

    def play(self, wav_path: str | Path) -> None:
        """Play a WAV file with the operating system's default application."""
        path = Path(wav_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"WAV file does not exist: {path}")

        if platform.system() == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return

        if sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
            return

        subprocess.Popen(["xdg-open", str(path)])

    def _post_json(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.api_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "audio/wav, audio/x-wav, application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return resp.read(), resp.headers.get("Content-Type", "")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else exc.reason
            raise RuntimeError(f"CosyVoice3 API failed with HTTP {exc.code}: {detail}") from exc
        except TimeoutError as exc:
            raise RuntimeError(f"CosyVoice3 API timed out after {self.timeout_seconds} seconds.") from exc
        except socket.timeout as exc:
            raise RuntimeError(f"CosyVoice3 API timed out after {self.timeout_seconds} seconds.") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Cannot connect to CosyVoice3 API at {self.api_url}: {exc.reason}") from exc
        except OSError as exc:
            raise RuntimeError(f"Cannot connect to CosyVoice3 API at {self.api_url}: {exc}") from exc

    def _extract_wav_bytes(self, response_body: bytes, content_type: str) -> bytes:
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type in {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}:
            return response_body
        if response_body.startswith(b"RIFF"):
            return response_body
        if media_type == "application/octet-stream" and self._looks_like_wav(response_body):
            return response_body
        if media_type == "application/json" or response_body.lstrip().startswith(b"{"):
            return self._extract_wav_from_json(response_body)
        guessed = mimetypes.guess_extension(media_type) if media_type else None
        raise RuntimeError(f"CosyVoice3 API did not return WAV audio. Content-Type={content_type!r}, guessed={guessed!r}")

    def _extract_wav_from_json(self, response_body: bytes) -> bytes:
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("CosyVoice3 API returned invalid JSON instead of WAV audio.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("CosyVoice3 API returned a non-object JSON response.")
        if payload.get("error"):
            raise RuntimeError(f"CosyVoice3 API error: {payload['error']}")
        if payload.get("ok") is False:
            raise RuntimeError(f"CosyVoice3 API failed: {payload}")

        for key in ("wav_base64", "audio_base64", "audio", "data"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                maybe_base64 = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
                try:
                    decoded = base64.b64decode(maybe_base64, validate=True)
                except Exception:
                    continue
                if self._looks_like_wav(decoded):
                    return decoded

        for key in ("wav_url", "audio_url", "url"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return self._download_audio(value)

        raise RuntimeError("CosyVoice3 API JSON response does not contain WAV audio data or an audio URL.")

    def _download_audio(self, audio_url: str) -> bytes:
        url = parse.urljoin(self.api_url, audio_url)
        try:
            with request.urlopen(url, timeout=self.timeout_seconds) as resp:
                data = resp.read()
        except Exception as exc:
            raise RuntimeError(f"Failed to download CosyVoice3 WAV audio from {url}: {exc}") from exc
        if not self._looks_like_wav(data):
            raise RuntimeError(f"Downloaded CosyVoice3 audio is not a WAV file: {url}")
        return data

    @staticmethod
    def _looks_like_wav(data: bytes) -> bool:
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"

    @staticmethod
    def _normalize_model_version(model_version: str) -> str:
        normalized = model_version.strip().lower()
        if normalized not in _VALID_MODEL_VERSIONS:
            raise ValueError("model_version must be 'base' or 'rl'.")
        return normalized


def speak(text: str, model_version: str = "base", api_url: str = _DEFAULT_TTS_URL, **extra_payload: Any) -> Path | None:
    """Convenience function for one-shot TTS synthesis and playback."""
    return TTSClient(api_url=api_url, model_version=model_version).speak(text, **extra_payload)
