from __future__ import annotations

import subprocess
import sys
from argparse import Namespace

import pytest

import scripts.start_cosyvoice3_windows as launcher


def _args(**overrides):
    values = {
        "conda_env": launcher.DEFAULT_CONDA_ENV,
        "service_dir": launcher.DEFAULT_SERVICE_DIR,
        "host": launcher.DEFAULT_HOST,
        "port": launcher.DEFAULT_PORT,
        "distro": launcher.DEFAULT_DISTRIBUTION,
        "terminal": "background",
        "log_file": launcher.DEFAULT_LOG_FILE,
        "pid_file": launcher.DEFAULT_PID_FILE,
        "print_command": False,
        "dry_run": False,
        "tail_lines": 120,
    }
    values.update(overrides)
    return Namespace(**values)


def _run_main(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr(launcher.platform, "system", lambda: "Windows")
    monkeypatch.setattr(sys, "argv", ["start_cosyvoice3_windows.py", *argv])
    return launcher.main()


def test_default_service_dir_is_absolute_wsl_path():
    assert launcher.DEFAULT_SERVICE_DIR == "/home/shakamilo/sylphos_services/cosyvoice3"
    assert not launcher.DEFAULT_SERVICE_DIR.startswith("~/")


def test_default_background_command_does_not_use_windows_terminal():
    command = launcher.build_start_command(_args())

    assert command[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
    assert command[4:6] == ["bash", "-lc"]
    assert "wt.exe" not in command


def test_default_background_script_starts_uvicorn_with_nohup_and_writes_log_and_pid():
    command = launcher.build_start_command(_args())
    bash_script = command[-1]

    assert "nohup uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880" in bash_script
    assert f"> '{launcher.DEFAULT_LOG_FILE}' 2>&1 &" in bash_script
    assert f"echo $! > '{launcher.DEFAULT_PID_FILE}'" in bash_script


def test_restart_kills_old_pid_before_launching(monkeypatch):
    events = []
    run_commands = []

    def fake_run(command, **kwargs):
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def fake_launch(args):
        events.append("launch")
        return subprocess.CompletedProcess(["wsl.exe"], 0, stdout="started\n", stderr="")

    monkeypatch.setattr(launcher, "read_wsl_uvicorn_pid", lambda distro, pid_file: "4321")
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher, "launch_service", fake_launch)
    monkeypatch.setattr(launcher, "wait_for_health", lambda health_url, timeout, poll_interval, args: {"ok": True})

    result = _run_main(monkeypatch, ["--restart", "--no-test"])

    assert result == 0
    assert ["wsl.exe", "-d", "Ubuntu", "--", "kill", "4321"] in run_commands
    assert ["wsl.exe", "-d", "Ubuntu", "--", "rm", "-f", launcher.DEFAULT_PID_FILE] in run_commands
    assert events == ["launch"]


def test_stop_only_kills_without_launching_or_testing(monkeypatch):
    run_commands = []

    def fake_run(command, **kwargs):
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(launcher, "read_wsl_uvicorn_pid", lambda distro, pid_file: "9876")
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher, "launch_service", lambda args: pytest.fail("--stop must not launch"))
    monkeypatch.setattr(launcher, "wait_for_health", lambda *args: pytest.fail("--stop must not wait for health"))
    monkeypatch.setattr(launcher, "synthesize_test_wav", lambda **kwargs: pytest.fail("--stop must not run TTS"))

    result = _run_main(monkeypatch, ["--stop"])

    assert result == 0
    assert ["wsl.exe", "-d", "Ubuntu", "--", "kill", "9876"] in run_commands


def test_tail_log_only_prints_log_without_launching_or_testing(monkeypatch):
    run_commands = []

    def fake_run(command, **kwargs):
        run_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="log tail\n", stderr="")

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    monkeypatch.setattr(launcher, "launch_service", lambda args: pytest.fail("--tail-log must not launch"))
    monkeypatch.setattr(launcher, "wait_for_health", lambda *args: pytest.fail("--tail-log must not wait for health"))
    monkeypatch.setattr(launcher, "synthesize_test_wav", lambda **kwargs: pytest.fail("--tail-log must not run TTS"))

    result = _run_main(monkeypatch, ["--tail-log"])

    assert result == 0
    assert run_commands == [["wsl.exe", "-d", "Ubuntu", "--", "tail", "-n", "120", launcher.DEFAULT_LOG_FILE]]


def test_already_healthy_does_not_start_duplicate_service(monkeypatch):
    monkeypatch.setattr(launcher, "query_health", lambda health_url: ("healthy", {"ok": True}, ""))
    monkeypatch.setattr(launcher, "launch_service", lambda args: pytest.fail("healthy service must not be launched again"))
    monkeypatch.setattr(launcher, "wait_for_health", lambda health_url, timeout, poll_interval, args: {"ok": True})

    result = _run_main(monkeypatch, ["--no-test"])

    assert result == 0


def test_wt_launch_command_separates_terminal_args_from_wsl_command():
    command = launcher.build_start_command(_args(terminal="wt", distro="Ubuntu-24.04"))

    assert command[:4] == ["wt.exe", "new-tab", "--title", "CosyVoice3 uvicorn"]
    title_index = command.index("--title")
    assert command[title_index + 1] == "CosyVoice3 uvicorn"
    assert command[title_index + 2] == "--"
    assert command[title_index + 3 : title_index + 7] == ["wsl.exe", "-d", "Ubuntu-24.04", "--"]
    assert command[title_index + 7 : title_index + 10] == ["bash", "-lc", command[-1]]


def test_dry_run_prints_command_without_launching(monkeypatch, capsys):
    monkeypatch.setattr(launcher.subprocess, "run", lambda *args, **kwargs: pytest.fail("dry-run must not run subprocess"))
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("dry-run must not launch subprocess"))

    process = launcher.launch_service(_args(dry_run=True, print_command=True))

    assert process is None
    output = capsys.readouterr().out
    assert '"wsl.exe"' in output
    assert "nohup uvicorn" in output
