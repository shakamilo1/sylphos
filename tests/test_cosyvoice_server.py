from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_cosyvoice_server_file_exists() -> None:
    assert Path("services/cosyvoice3/cosyvoice_server.py").is_file()


def test_import_app() -> None:
    pytest.importorskip("fastapi")
    module = importlib.import_module("services.cosyvoice3.cosyvoice_server")
    assert module.app is not None


def test_health_without_cosyvoice_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    server = importlib.import_module("services.cosyvoice3.cosyvoice_server")

    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "cosyvoice.cli.cosyvoice":
            raise ModuleNotFoundError("No module named 'cosyvoice'")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    monkeypatch.setattr(server, "_engine", None)
    monkeypatch.setattr(server, "_engine_errors", [])

    response = TestClient(server.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "cosyvoice3"
    assert payload["ok"] is False
    assert payload["cosyvoice_loaded"] is False
    assert payload["errors"]
    assert "CosyVoice" in payload["errors"][0] or "cosyvoice" in payload["errors"][0]
