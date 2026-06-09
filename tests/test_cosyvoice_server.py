from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture()
def server(monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    module = importlib.import_module("services.cosyvoice3.cosyvoice_server")
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
    from fastapi.testclient import TestClient

    repo = tmp_path / "CosyVoice"
    repo.mkdir()
    model = _make_model_dir(tmp_path)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(model))

    response = TestClient(server.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["cosyvoice_importable"] is False
    assert payload["cosyvoice_loaded"] is False
    assert any("cosyvoice/cli/cosyvoice.py" in error for error in payload["errors"])
    assert any("Current sys.path" in error for error in payload["errors"])


def test_health_reports_missing_model_path(server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    repo = _make_cosyvoice_repo(tmp_path)
    missing_model = tmp_path / "pretrained_models" / "Fun-CosyVoice3-0.5B"
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(missing_model))

    response = TestClient(server.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
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


def test_create_runtime_uses_selected_model_path_with_mocked_automodel(
    server, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = _make_cosyvoice_repo(tmp_path)
    base = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B")
    rl = _make_model_dir(tmp_path, "Fun-CosyVoice3-0.5B-rl")
    calls = []

    class FakeAutoModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_module = types.SimpleNamespace(AutoModel=FakeAutoModel)
    monkeypatch.setenv("COSYVOICE_REPO", str(repo))
    monkeypatch.setenv("COSYVOICE_MODEL_PATH", str(base))
    monkeypatch.setenv("COSYVOICE_RL_MODEL_PATH", str(rl))
    monkeypatch.setattr(server, "_module_exists", lambda name: name == "cosyvoice.cli.cosyvoice")
    monkeypatch.setattr(importlib, "import_module", lambda name: fake_module if name == "cosyvoice.cli.cosyvoice" else importlib.import_module(name))

    server._create_runtime("rl")

    assert calls[0]["model_dir"] == str(rl)
