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


def test_windows_auto_play_prefers_winsound(monkeypatch, tmp_path):
    import sys
    import types
    import sylphos.voice.tts.wsl_cosyvoice_client as client_module

    wav_path = tmp_path / "sound.wav"
    wav_path.write_bytes(WAV_BYTES)
    calls = []
    fake_winsound = types.SimpleNamespace(
        SND_FILENAME=0x20000,
        PlaySound=lambda path, flags: calls.append((path, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    monkeypatch.setattr(client_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(client_module.os, "startfile", lambda path: calls.append(("startfile", path)), raising=False)

    TTSClient(auto_play=False, play_backend="auto").play(wav_path)

    assert calls == [(str(wav_path.resolve()), fake_winsound.SND_FILENAME)]


def test_windows_auto_play_falls_back_to_default_app_when_winsound_fails(monkeypatch, tmp_path, capsys):
    import sys
    import types
    import sylphos.voice.tts.wsl_cosyvoice_client as client_module

    wav_path = tmp_path / "sound.wav"
    wav_path.write_bytes(WAV_BYTES)
    calls = []

    def fail_play_sound(path, flags):
        raise RuntimeError("audio device busy")

    fake_winsound = types.SimpleNamespace(SND_FILENAME=0x20000, PlaySound=fail_play_sound)
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    monkeypatch.setattr(client_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(client_module.os, "startfile", lambda path: calls.append(path), raising=False)

    TTSClient(auto_play=False, play_backend="auto").play(wav_path)

    assert calls == [str(wav_path.resolve())]
    assert "winsound playback failed" in capsys.readouterr().err


def test_default_app_backend_uses_existing_windows_startfile_behavior(monkeypatch, tmp_path):
    import sys
    import types
    import sylphos.voice.tts.wsl_cosyvoice_client as client_module

    wav_path = tmp_path / "sound.wav"
    wav_path.write_bytes(WAV_BYTES)
    calls = []
    fake_winsound = types.SimpleNamespace(
        SND_FILENAME=0x20000,
        PlaySound=lambda path, flags: calls.append(("winsound", path, flags)),
    )
    monkeypatch.setitem(sys.modules, "winsound", fake_winsound)
    monkeypatch.setattr(client_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(client_module.os, "startfile", lambda path: calls.append(("startfile", path)), raising=False)

    TTSClient(auto_play=False, play_backend="default_app").play(wav_path)

    assert calls == [("startfile", str(wav_path.resolve()))]


def test_non_windows_auto_play_keeps_xdg_open_fallback(monkeypatch, tmp_path):
    import sylphos.voice.tts.wsl_cosyvoice_client as client_module

    wav_path = tmp_path / "sound.wav"
    wav_path.write_bytes(WAV_BYTES)
    calls = []
    monkeypatch.setattr(client_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(client_module.sys, "platform", "linux")
    monkeypatch.setattr(client_module.subprocess, "Popen", lambda args: calls.append(args))

    TTSClient(auto_play=False, play_backend="auto").play(wav_path)

    assert calls == [["xdg-open", str(wav_path.resolve())]]


def test_rejects_invalid_play_backend():
    try:
        TTSClient(play_backend="bad")
    except ValueError as exc:
        assert "auto" in str(exc)
        assert "winsound" in str(exc)
        assert "default_app" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
