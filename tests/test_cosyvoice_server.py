from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


WAV_BYTES = b"RIFF$\x00\x00\x00WAVEfmt " + b"\x00" * 24


def _install_fastapi_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    if importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("pydantic") is not None:
        return

    class FakeFastAPI:
        def __init__(self, *args, **kwargs) -> None:
            self.routes = []

        def get(self, path: str):
            def decorator(func):
                self.routes.append(("GET", path, func))
                return func

            return decorator

        def post(self, path: str):
            def decorator(func):
                self.routes.append(("POST", path, func))
                return func

            return decorator

    class FakeResponse:
        def __init__(self, content=b"", status_code: int = 200, media_type: str | None = None) -> None:
            self.body = content if isinstance(content, bytes) else str(content).encode("utf-8")
            self.status_code = status_code
            self.media_type = media_type
            self.headers = {"content-type": media_type or ""}

    class FakeBaseModel:
        def __init__(self, **kwargs) -> None:
            for key, value in kwargs.items():
                setattr(self, key, value)

    def fake_field(default=..., **kwargs):
        return default

    fastapi_module = types.ModuleType("fastapi")
    fastapi_module.FastAPI = FakeFastAPI
    responses_module = types.ModuleType("fastapi.responses")
    responses_module.Response = FakeResponse
    pydantic_module = types.ModuleType("pydantic")
    pydantic_module.BaseModel = FakeBaseModel
    pydantic_module.Field = fake_field
    monkeypatch.setitem(sys.modules, "fastapi", fastapi_module)
    monkeypatch.setitem(sys.modules, "fastapi.responses", responses_module)
    monkeypatch.setitem(sys.modules, "pydantic", pydantic_module)


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch):
    _install_fastapi_stubs(monkeypatch)
    module = importlib.import_module("services.cosyvoice3.cosyvoice_server")
    module = importlib.reload(module)
    module._reset_runtime_cache()
    yield module
    module._reset_runtime_cache()


def _make_cosyvoice_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "CosyVoice"
    package_dir = repo / "cosyvoice" / "cli"
    matcha_dir = repo / "third_party" / "Matcha-TTS"
    package_dir.mkdir(parents=True)
    matcha_dir.mkdir(parents=True)
    (repo / "cosyvoice" / "__init__.py").write_text("")
    (package_dir / "__init__.py").write_text("")
    (package_dir / "cosyvoice.py").write_text("class AutoModel:\n    def __init__(self, **kwargs):\n        self.kwargs = kwargs\n")
    return repo


def _make_model_dir(tmp_path: Path, name: str = "Fun-CosyVoice3-0.5B") -> Path:
    model = tmp_path / "pretrained_models" / name
    model.mkdir(parents=True)
    return model


def _request(text: str = "你好", model_version: str = "base"):
    return types.SimpleNamespace(
        text=text,
        output_path=None,
        prompt_wav=None,
        prompt_text=None,
        speaker=None,
        model_version=model_version,
    )


def test_cosyvoice_server_file_exists() -> None:
    assert Path("services/cosyvoice3/cosyvoice_server.py").is_file()


def test_import_app(server) -> None:
    assert server.app is not None


def test_cosyvoice_repo_env_adds_repo_and_matcha_to_sys_path(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setattr(sys, "path", [entry for entry in sys.path if str(repo) not in entry])

    server._ensure_cosyvoice_repo_on_path()

    assert str(repo) in sys.path
    assert str(repo / "third_party" / "Matcha-TTS") in sys.path
    assert sys.path.index(str(repo)) < sys.path.index(str(repo / "third_party" / "Matcha-TTS"))


def test_health_reports_missing_cosyvoice_py(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "CosyVoice"
    repo.mkdir()
    model = _make_model_dir(tmp_path)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(model))

    payload = server.health()

    assert payload["ok"] is False
    assert payload["cosyvoice_importable"] is False
    assert payload["cosyvoice_loaded"] is False
    assert any("cosyvoice/cli/cosyvoice.py" in error for error in payload["errors"])
    assert any("Current sys.path" in error for error in payload["errors"])


def test_health_reports_missing_model_path(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    missing_model = tmp_path / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(missing_model))

    payload = server.health()

    assert payload["ok"] is False
    assert payload["cosyvoice_loaded"] is False
    assert payload["cosyvoice_importable"] is True
    assert any("model path does not exist" in error for error in payload["errors"])
    assert str(missing_model) in payload["errors"][0]


def test_model_version_base_uses_base_model_path(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    rl = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B-rl")
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setenv("COSYVOICE_RL_MODEL_PATH", str(rl))

    assert server._model_path_for_version("base") == str(base)
    assert server._model_path_for_version(None) == str(base)


def test_model_version_rl_uses_rl_model_path(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    rl = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B-rl")
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setenv("COSYVOICE_RL_MODEL_PATH", str(rl))

    assert server._model_path_for_version("rl") == str(rl)


def test_create_runtime_uses_selected_model_path_without_device_arg(
    server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    rl = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B-rl")
    calls = []

    class FakeAutoModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    original_import_module = importlib.import_module
    fake_module = types.SimpleNamespace(AutoModel=FakeAutoModel)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setenv("COSYVOICE_RL_MODEL_PATH", str(rl))
    monkeypatch.setenv("COSYVOICE_DEVICE", "cuda")
    monkeypatch.setattr(server, "_module_exists", lambda name: name == "cosyvoice.cli.cosyvoice")
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, package=None: fake_module if name == "cosyvoice.cli.cosyvoice" else original_import_module(name, package),
    )

    server._create_runtime("rl")

    assert calls == [{"model_dir": str(rl)}]
    assert "device" not in calls[0]


def test_health_reports_model_load_failure(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")

    class BrokenAutoModel:
        def __init__(self, **kwargs):
            raise RuntimeError("load boom")

    fake_module = types.SimpleNamespace(AutoModel=BrokenAutoModel)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setattr(server, "_module_exists", lambda name: name == "cosyvoice.cli.cosyvoice")
    monkeypatch.setattr(importlib, "import_module", lambda name, package=None: fake_module)

    payload = server.health()

    assert payload["ok"] is False
    assert payload["cosyvoice_importable"] is True
    assert payload["cosyvoice_loaded"] is False
    assert any("load boom" in error for error in payload["errors"])


def test_v1_tts_returns_503_when_model_not_loaded(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    missing_model = tmp_path / "missing-model"
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(missing_model))

    response = server.tts_v1(_request())

    assert response.status_code == 503
    assert b'"ok": false' in response.body
    assert b'"cosyvoice_loaded": false' in response.body
    assert b"model path does not exist" in response.body


def test_v1_tts_returns_500_when_synthesis_fails(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FailingRuntime:
        def synthesize_to_file(self, *args, **kwargs):
            raise RuntimeError("synthesis boom")

    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setattr(server, "_get_runtime", lambda version: (FailingRuntime(), []))

    response = server.tts_v1(_request())

    assert response.status_code == 500
    assert b'"ok": false' in response.body
    assert b"synthesis boom" in response.body


def test_v1_tts_returns_wav_bytes_on_success(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class SuccessfulRuntime:
        def synthesize_to_file(self, text, output_path, **kwargs):
            Path(output_path).write_bytes(WAV_BYTES)

    output_path = tmp_path / "out.wav"
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setattr(server, "_get_runtime", lambda version: (SuccessfulRuntime(), []))
    request = _request()
    request.output_path = str(output_path)

    response = server.tts_v1(request)

    assert response.status_code == 200
    assert "audio/wav" in (response.media_type or response.headers.get("content-type", ""))
    assert response.body.startswith(b"RIFF")
