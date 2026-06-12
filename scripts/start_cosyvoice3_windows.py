#!/usr/bin/env python3
from __future__ import annotations

"""Start the CosyVoice3 WSL2 service from Windows and run a smoke TTS test.

Default mode is intentionally non-interactive and stable: Windows Python calls
``wsl.exe -d Ubuntu -- bash -lc <script>``; the WSL script starts uvicorn with
``nohup`` in the background, writes logs and a PID file inside WSL, then returns
control to Windows. The Windows process polls /health, performs one TTS warm-up,
saves a WAV under %TEMP%, plays it with winsound, and exits while the WSL service
keeps running.
"""

import argparse
import base64
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_DISTRIBUTION = "Ubuntu"
DEFAULT_CONDA_ENV = "cosyvoice3"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9880
DEFAULT_HEALTH_TIMEOUT_SECONDS = 600.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_SERVICE_DIR = "/home/shakamilo/sylphos_services/cosyvoice3"
DEFAULT_LOG_FILE = "/home/shakamilo/sylphos_services/cosyvoice3/cosyvoice3_service.log"
DEFAULT_PID_FILE = "/tmp/sylphos_cosyvoice3_uvicorn.pid"
DEFAULT_TEST_TEXT = "你好，Sylphos。CosyVoice3 服务启动并预热成功。"
DEFAULT_VOICE_ID = "official"
DEFAULT_MODEL_VERSION = "base"

WSL_ENVIRONMENT = {
    "COSYVOICE_REPO": "/home/shakamilo/CosyVoice",
    "COSYVOICE_MODEL_PATH": "/home/shakamilo/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B",
    "COSYVOICE_RL_MODEL_PATH": "/home/shakamilo/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl",
    "COSYVOICE_PROMPT_DIR": "/home/shakamilo/sylphos_services/cosyvoice3/prompts",
}


def shell_quote(value: str) -> str:
    """Quote a string for POSIX shell usage inside WSL."""

    return "'" + value.replace("'", "'\"'\"'") + "'"


def health_url_for_port(port: int) -> str:
    return f"http://127.0.0.1:{port}/health"


def tts_url_for_port(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1/tts"


def build_conda_bootstrap(conda_env: str) -> str:
    """Return robust conda activation lines for the WSL bash script."""

    return f"""if [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  . "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  . "$HOME/miniconda3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
  . "$(conda info --base)/etc/profile.d/conda.sh"
else
  echo "[CosyVoice3] ERROR: conda not found. Install Anaconda/Miniconda in WSL2 first." >&2
  exit 127
fi
conda activate {shell_quote(conda_env)}"""


def build_env_exports(extra_env: dict[str, str] | None = None) -> str:
    env = {**WSL_ENVIRONMENT, **(extra_env or {})}
    return "\n".join(f"export {name}={shell_quote(value)}" for name, value in env.items())


def build_background_start_script(
    *,
    conda_env: str,
    service_dir: str,
    host: str,
    port: int,
    log_file: str,
    pid_file: str,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Build the WSL script that starts uvicorn with nohup and returns."""

    return f"""set -Eeuo pipefail
cd {shell_quote(service_dir)}
{build_conda_bootstrap(conda_env)}
{build_env_exports(extra_env)}
mkdir -p "$(dirname {shell_quote(log_file)})" "$(dirname {shell_quote(pid_file)})"
if [ -f {shell_quote(pid_file)} ] && kill -0 "$(cat {shell_quote(pid_file)})" 2>/dev/null; then
  echo "[CosyVoice3] Existing uvicorn process is still running: $(cat {shell_quote(pid_file)})"
  exit 0
fi
nohup uvicorn cosyvoice_server:app --host {host} --port {port} > {shell_quote(log_file)} 2>&1 &
echo $! > {shell_quote(pid_file)}
echo "[CosyVoice3] Started uvicorn PID $(cat {shell_quote(pid_file)})"
echo "[CosyVoice3] Log file: {log_file}"
"""


def build_foreground_start_script(
    *,
    conda_env: str,
    service_dir: str,
    host: str,
    port: int,
    pid_file: str,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Build the optional visible-window script that keeps uvicorn in foreground."""

    return f"""set -Eeuo pipefail
cd {shell_quote(service_dir)}
{build_conda_bootstrap(conda_env)}
{build_env_exports(extra_env)}
echo $$ > {shell_quote(pid_file)}
echo "[CosyVoice3] Uvicorn PID will be $$ after exec."
echo "[CosyVoice3] Press Ctrl+C in this window to stop the service."
exec uvicorn cosyvoice_server:app --host {host} --port {port}
"""


def build_wsl_bash_command(distro: str, bash_script: str) -> list[str]:
    return ["wsl.exe", "-d", distro, "--", "bash", "-lc", bash_script]


def build_start_command(args: argparse.Namespace) -> list[str]:
    """Build the command used for the selected launch mode."""

    if args.terminal == "background":
        script = build_background_start_script(
            conda_env=args.conda_env,
            service_dir=args.service_dir,
            host=args.host,
            port=args.port,
            log_file=args.log_file,
            pid_file=args.pid_file,
        )
        return build_wsl_bash_command(args.distro, script)

    script = build_foreground_start_script(
        conda_env=args.conda_env,
        service_dir=args.service_dir,
        host=args.host,
        port=args.port,
        pid_file=args.pid_file,
    )
    wsl_command = build_wsl_bash_command(args.distro, script)
    if args.terminal == "wt":
        return ["wt.exe", "new-tab", "--title", "CosyVoice3 uvicorn", "--", *wsl_command]
    return wsl_command


def print_launch_command(command: list[str]) -> None:
    """Print the exact argv and escaped command line for debugging."""

    print("[Windows] Launch command argv:")
    print(json.dumps(command, ensure_ascii=False, indent=2))
    print("[Windows] Launch command line:")
    print(subprocess.list2cmdline(command))


def launch_service(args: argparse.Namespace) -> subprocess.CompletedProcess[str] | subprocess.Popen[Any] | None:
    """Start the service in background mode by default, or optional window mode."""

    command = build_start_command(args)
    if args.print_command or args.dry_run:
        print_launch_command(command)
    if args.dry_run:
        return None

    if args.terminal == "wt":
        if not shutil.which("wt.exe"):
            raise RuntimeError("wt.exe was requested but Windows Terminal was not found on PATH.")
        print("[Windows] Opening Windows Terminal tab for CosyVoice3 uvicorn logs...")
        return subprocess.Popen(command)

    if args.terminal == "wsl":
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        print("[Windows] Opening a standalone WSL console for CosyVoice3 uvicorn logs...")
        return subprocess.Popen(command, creationflags=creationflags)

    print("[Windows] Starting CosyVoice3 uvicorn in WSL background mode...")
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=30.0)


# Backward-compatible name used by older tests/review comments.
def launch_service_window(args: argparse.Namespace) -> subprocess.CompletedProcess[str] | subprocess.Popen[Any] | None:
    return launch_service(args)


def read_wsl_uvicorn_pid(distro: str, pid_file: str = DEFAULT_PID_FILE) -> str | None:
    try:
        completed = subprocess.run(
            ["wsl.exe", "-d", distro, "--", "cat", pid_file],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    pid = completed.stdout.strip()
    return pid if pid.isdigit() else None


def stop_service(args: argparse.Namespace) -> bool:
    """Kill the uvicorn process recorded in the WSL PID file."""

    pid = read_wsl_uvicorn_pid(args.distro, args.pid_file)
    if not pid:
        print(f"[Windows] No uvicorn PID found in WSL file: {args.pid_file}")
        return False

    print(f"[Windows] Stopping CosyVoice3 uvicorn PID {pid} in WSL distro {args.distro}...")
    subprocess.run(["wsl.exe", "-d", args.distro, "--", "kill", pid], check=False, text=True, timeout=10.0)
    subprocess.run(["wsl.exe", "-d", args.distro, "--", "rm", "-f", args.pid_file], check=False, text=True, timeout=10.0)
    print("[Windows] Stop command sent.")
    return True


def tail_log(args: argparse.Namespace, lines: int | None = None) -> subprocess.CompletedProcess[str]:
    line_count = str(lines or args.tail_lines)
    command = ["wsl.exe", "-d", args.distro, "--", "tail", "-n", line_count, args.log_file]
    print(f"[Windows] Log command: {subprocess.list2cmdline(command)}")
    completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=15.0)
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed


def query_health(health_url: str, timeout_seconds: float = 5.0) -> tuple[str, dict[str, Any] | None, str]:
    """Return (healthy|unhealthy|unreachable, payload, error)."""

    try:
        with request.urlopen(health_url, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = None
        return "unhealthy", payload, f"HTTP {exc.code}: {exc.reason}"
    except error.URLError as exc:
        return "unreachable", None, str(exc.reason)
    except TimeoutError:
        return "unreachable", None, "health request timed out"
    except OSError as exc:
        return "unreachable", None, str(exc)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return "unhealthy", None, f"invalid JSON: {exc}"
    if payload.get("ok") is True:
        return "healthy", payload, ""
    return "unhealthy", payload, "health returned ok=false"


def wait_for_health(health_url: str, timeout_seconds: float, poll_interval: float, args: argparse.Namespace) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "health endpoint was not contacted"

    while time.monotonic() < deadline:
        state, payload, health_error = query_health(health_url)
        if state == "healthy" and payload is not None:
            print(f"[Windows] Health check passed: {health_url}")
            return payload
        last_error = health_error or (json.dumps(payload, ensure_ascii=False) if payload is not None else state)
        remaining = max(0.0, deadline - time.monotonic())
        print(f"[Windows] Waiting for /health ... remaining {remaining:.0f}s")
        time.sleep(poll_interval)

    print(f"[Windows] ERROR: CosyVoice3 did not become healthy. Last error: {last_error}", file=sys.stderr)
    print(
        "[Windows] View logs with: "
        f"wsl -d {args.distro} -- tail -n 80 {args.log_file}",
        file=sys.stderr,
    )
    print("[Windows] Last 80 log lines:", file=sys.stderr)
    tail_log(args, lines=80)
    raise TimeoutError(f"CosyVoice3 did not become healthy within {timeout_seconds:.0f}s: {last_error}")


def synthesize_test_wav(
    *,
    tts_url: str,
    text: str,
    voice_id: str,
    model_version: str,
    timeout_seconds: float,
) -> Path:
    payload = {
        "text": text,
        "model_version": model_version,
        "voice_id": voice_id,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        tts_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "audio/wav, application/json"},
        method="POST",
    )
    print(f"[Windows] Calling warm-up TTS endpoint: {tts_url}")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else exc.reason
        raise RuntimeError(f"TTS request failed with HTTP {exc.code}: {detail}") from exc

    wav_bytes = extract_wav_bytes(response_body, content_type)
    output_dir = Path(tempfile.gettempdir()) / "sylphos_tts"
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / f"cosyvoice3_startup_test_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
    wav_path.write_bytes(wav_bytes)
    print(f"[Windows] Saved warm-up WAV: {wav_path}")
    return wav_path


def extract_wav_bytes(response_body: bytes, content_type: str) -> bytes:
    media_type = content_type.split(";", 1)[0].strip().lower()
    if response_body.startswith(b"RIFF") and response_body[8:12] == b"WAVE":
        return response_body
    if media_type == "application/json" or response_body.lstrip().startswith(b"{"):
        payload = json.loads(response_body.decode("utf-8"))
        if payload.get("ok") is False:
            raise RuntimeError(f"TTS API returned an error: {payload}")
        for key in ("wav_base64", "audio_base64", "audio", "data"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                raw = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
                decoded = base64.b64decode(raw)
                if decoded.startswith(b"RIFF") and decoded[8:12] == b"WAVE":
                    return decoded
    raise RuntimeError(f"TTS API did not return WAV audio. Content-Type={content_type!r}")


def play_wav(path: Path) -> None:
    import winsound

    print(f"[Windows] Playing warm-up WAV with winsound: {path}")
    winsound.PlaySound(str(path), winsound.SND_FILENAME)


def print_runtime_summary(args: argparse.Namespace, health_url: str) -> None:
    print(f"[Windows] WSL distro: {args.distro}")
    print(f"[Windows] Health URL: {health_url}")
    print(f"[Windows] WSL log file: {args.log_file}")
    print(f"[Windows] WSL PID file: {args.pid_file}")
    print(f"[Windows] Stop command: wsl -d {args.distro} -- bash -lc 'kill $(cat {args.pid_file})'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start CosyVoice3 in WSL2 background mode, wait for health, warm up TTS, and play the test WAV.",
    )
    parser.add_argument("--distro", default=DEFAULT_DISTRIBUTION, help="WSL distribution name, e.g. Ubuntu or Ubuntu-24.04.")
    parser.add_argument(
        "--terminal",
        choices=["background", "wt", "wsl"],
        default="background",
        help="Launch mode: background nohup (default), Windows Terminal tab, or standalone WSL console.",
    )
    parser.add_argument("--no-launch", action="store_true", help="Do not start a new service; only wait for health and optionally test.")
    parser.add_argument("--restart", action="store_true", help="Kill the PID recorded in WSL, then start a fresh service.")
    parser.add_argument("--stop", action="store_true", help="Kill the PID recorded in WSL and exit without health/TTS checks.")
    parser.add_argument("--tail-log", action="store_true", help="Print the WSL service log tail and exit without starting/testing.")
    parser.add_argument("--tail-lines", type=int, default=120, help="Number of log lines to print with --tail-log.")
    parser.add_argument("--print-command", action="store_true", help="Print the final wt.exe/wsl.exe command before launching.")
    parser.add_argument("--dry-run", action="store_true", help="Print the final launch command and exit without launching/testing.")
    parser.add_argument("--conda-env", default=DEFAULT_CONDA_ENV, help="Conda environment to activate inside WSL.")
    parser.add_argument("--service-dir", default=DEFAULT_SERVICE_DIR, help="CosyVoice3 service directory inside WSL.")
    parser.add_argument("--log-file", default=DEFAULT_LOG_FILE, help="WSL path for uvicorn stdout/stderr logs.")
    parser.add_argument("--pid-file", default=DEFAULT_PID_FILE, help="WSL path for the uvicorn PID file.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="uvicorn host inside WSL.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="uvicorn port exposed to Windows localhost.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_HEALTH_TIMEOUT_SECONDS, help="Seconds to wait for health and TTS.")
    parser.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS, help="Seconds between health checks.")
    parser.add_argument("--no-test", action="store_true", help="Skip the /v1/tts warm-up test after health succeeds.")
    parser.add_argument("--text", default=DEFAULT_TEST_TEXT, help="Warm-up text to synthesize.")
    parser.add_argument("--voice-id", default=DEFAULT_VOICE_ID, help="voice_id sent to /v1/tts.")
    parser.add_argument("--model-version", choices=["base", "rl"], default=DEFAULT_MODEL_VERSION, help="CosyVoice model version.")
    return parser.parse_args()


def main() -> int:
    if platform.system() != "Windows":
        print("ERROR: This script is intended to be run by Windows Python, not inside WSL/Linux.", file=sys.stderr)
        return 2

    args = parse_args()
    health_url = health_url_for_port(args.port)
    tts_url = tts_url_for_port(args.port)
    print_runtime_summary(args, health_url)

    if args.tail_log:
        return tail_log(args).returncode

    if args.stop:
        stop_service(args)
        return 0

    if args.restart:
        stop_service(args)
    elif not args.no_launch:
        state, payload, health_error = query_health(health_url)
        if state == "healthy":
            print("[Windows] CosyVoice3 is already healthy; not starting another uvicorn process.")
        elif state == "unhealthy":
            print("[Windows] CosyVoice3 port responded but /health is not healthy; not starting a duplicate service.", file=sys.stderr)
            if payload is not None:
                print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
            else:
                print(f"[Windows] Health error: {health_error}", file=sys.stderr)
            print("[Windows] Use --restart to kill the recorded PID and start again.", file=sys.stderr)
            return 1
        else:
            launched = launch_service(args)
            if launched is None:
                print("[Windows] Dry run completed; service was not launched.")
                return 0
            if isinstance(launched, subprocess.CompletedProcess):
                if launched.stdout:
                    print(launched.stdout, end="")
                if launched.stderr:
                    print(launched.stderr, end="", file=sys.stderr)
    elif args.dry_run:
        print_launch_command(build_start_command(args))
        print("[Windows] Dry run completed; service was not launched.")
        return 0

    if args.restart:
        launched = launch_service(args)
        if launched is None:
            print("[Windows] Dry run completed; service was not launched.")
            return 0
        if isinstance(launched, subprocess.CompletedProcess):
            if launched.stdout:
                print(launched.stdout, end="")
            if launched.stderr:
                print(launched.stderr, end="", file=sys.stderr)

    health_payload = wait_for_health(health_url, args.timeout, args.poll_interval, args)
    print(f"[Windows] Service health OK: {json.dumps(health_payload, ensure_ascii=False, indent=2)}")

    if args.no_test:
        print("[Windows] --no-test was set; skipping warm-up TTS.")
        return 0

    wav_path = synthesize_test_wav(
        tts_url=tts_url,
        text=args.text,
        voice_id=args.voice_id,
        model_version=args.model_version,
        timeout_seconds=args.timeout,
    )
    play_wav(wav_path)
    print("[Windows] CosyVoice3 startup warm-up completed successfully.")
    print(f"[Windows] WAV file remains available at: {wav_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
