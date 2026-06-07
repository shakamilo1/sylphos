from __future__ import annotations

import base64
import json
from urllib import error

from sylphos.voice.tts.wsl_cosyvoice_client import TTSClient


WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 24


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "audio/wav") -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.body


def test_synthesize_to_file_posts_text_and_model_version(monkeypatch, tmp_path):
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req, timeout))
        return FakeResponse(WAV_BYTES)

    monkeypatch.setattr("sylphos.voice.tts.wsl_cosyvoice_client.request.urlopen", fake_urlopen)
    client = TTSClient(model_version="rl", timeout_seconds=7, auto_play=False)

    output = client.synthesize_to_file(" 你好 ", tmp_path / "out.wav")

    assert output.read_bytes() == WAV_BYTES
    req, timeout = calls[0]
    assert req.full_url == "http://127.0.0.1:9880/v1/tts"
    assert timeout == 7
    assert req.get_method() == "POST"
    assert req.headers["Content-type"] == "application/json"
    body = json.loads(req.data.decode("utf-8"))
    assert body == {"text": "你好", "model_version": "rl"}


def test_speak_saves_each_call_and_invokes_player(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sylphos.voice.tts.wsl_cosyvoice_client.request.urlopen",
        lambda req, timeout: FakeResponse(WAV_BYTES),
    )
    played = []
    client = TTSClient(temp_dir=tmp_path)
    monkeypatch.setattr(client, "play", lambda wav_path: played.append(wav_path))

    first = client.speak("第一句")
    second = client.speak("第二句")

    assert first is not None
    assert second is not None
    assert first != second
    assert first.read_bytes() == WAV_BYTES
    assert second.read_bytes() == WAV_BYTES
    assert played == [first, second]


def test_json_base64_audio_response(monkeypatch, tmp_path):
    payload = {"wav_base64": base64.b64encode(WAV_BYTES).decode("ascii")}
    monkeypatch.setattr(
        "sylphos.voice.tts.wsl_cosyvoice_client.request.urlopen",
        lambda req, timeout: FakeResponse(json.dumps(payload).encode("utf-8"), "application/json"),
    )

    output = TTSClient(auto_play=False).synthesize_to_file("你好", tmp_path / "json.wav")

    assert output.read_bytes() == WAV_BYTES


def test_speak_prints_error_and_returns_none(monkeypatch, capsys):
    def fake_urlopen(req, timeout):
        raise error.URLError("connection refused")

    monkeypatch.setattr("sylphos.voice.tts.wsl_cosyvoice_client.request.urlopen", fake_urlopen)

    result = TTSClient(auto_play=False).speak("你好")

    assert result is None
    assert "Cannot connect to CosyVoice3 API" in capsys.readouterr().err


def test_rejects_invalid_model_version():
    try:
        TTSClient(model_version="bad")
    except ValueError as exc:
        assert "base" in str(exc)
        assert "rl" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
