from __future__ import annotations

from argparse import Namespace

import scripts.start_cosyvoice3_windows as launcher


def _args(**overrides):
    values = {
        "conda_env": launcher.DEFAULT_CONDA_ENV,
        "service_dir": launcher.DEFAULT_SERVICE_DIR,
        "host": launcher.DEFAULT_HOST,
        "port": launcher.DEFAULT_PORT,
        "distro": launcher.DEFAULT_DISTRIBUTION,
        "terminal": "wt",
        "print_command": False,
        "dry_run": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_wt_launch_command_separates_terminal_args_from_wsl_command(monkeypatch):
    calls = []

    class FakeProcess:
        pid = 1234

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(launcher.shutil, "which", lambda name: "C:/WindowsApps/wt.exe" if name == "wt.exe" else None)
    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    process = launcher.launch_service_window(_args(terminal="wt", distro="Ubuntu-24.04"))

    assert process.pid == 1234
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert kwargs == {}
    assert command[:4] == ["wt.exe", "new-tab", "--title", "CosyVoice3 uvicorn"]
    title_index = command.index("--title")
    assert command[title_index + 1] == "CosyVoice3 uvicorn"
    assert command[title_index + 2] == "--"
    assert command[title_index + 3 : title_index + 7] == ["wsl.exe", "-d", "Ubuntu-24.04", "--"]
    assert command[title_index + 7 : title_index + 10] == ["bash", "-lc", command[-1]]


def test_wsl_launch_command_does_not_use_windows_terminal(monkeypatch):
    calls = []

    class FakeProcess:
        pid = 5678

    def fake_popen(command, **kwargs):
        calls.append((command, kwargs))
        return FakeProcess()

    monkeypatch.setattr(launcher.subprocess, "Popen", fake_popen)

    process = launcher.launch_service_window(_args(terminal="wsl", distro="Ubuntu"))

    assert process.pid == 5678
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
    assert command[4:6] == ["bash", "-lc"]
    assert "wt.exe" not in command
    assert "CREATE_NEW_CONSOLE" not in kwargs
    assert "creationflags" in kwargs


def test_default_service_dir_is_absolute_wsl_path():
    assert launcher.DEFAULT_SERVICE_DIR == "/home/shakamilo/sylphos_services/cosyvoice3"
    assert not launcher.DEFAULT_SERVICE_DIR.startswith("~/")


def test_dry_run_prints_command_without_launching(monkeypatch, capsys):
    def fail_popen(command, **kwargs):
        raise AssertionError("dry-run must not launch a subprocess")

    monkeypatch.setattr(launcher.shutil, "which", lambda name: "C:/WindowsApps/wt.exe" if name == "wt.exe" else None)
    monkeypatch.setattr(launcher.subprocess, "Popen", fail_popen)

    process = launcher.launch_service_window(_args(terminal="wt", dry_run=True))

    assert process is None
    output = capsys.readouterr().out
    assert '"wt.exe"' in output
    assert '"--"' in output
