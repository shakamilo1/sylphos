from __future__ import annotations

import pytest

from sylphos.config.loader import load_config


def test_load_config_reads_root_local_config(monkeypatch, tmp_path):
    (tmp_path / "local_config.py").write_text(
        'TOOL_EXECUTOR_PROVIDER = "openclaw"\n'
        'OPENCLAW_MODE = "cli"\n'
        'OPENCLAW_DRY_RUN = True\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.TOOL_EXECUTOR_PROVIDER == "openclaw"
    assert config.OPENCLAW_MODE == "cli"
    assert config.OPENCLAW_DRY_RUN is True


def test_load_config_env_overrides_root_local_config(monkeypatch, tmp_path):
    (tmp_path / "local_config.py").write_text('TOOL_EXECUTOR_PROVIDER = "openclaw"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOOL_EXECUTOR_PROVIDER", "dummy")

    config = load_config()

    assert config.TOOL_EXECUTOR_PROVIDER == "dummy"


def test_load_config_reports_root_local_config_syntax_errors(monkeypatch, tmp_path):
    (tmp_path / "local_config.py").write_text("TOOL_EXECUTOR_PROVIDER = ", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="local_config.py"):
        load_config()
