#!/usr/bin/env python3
from __future__ import annotations

"""Launch the CosyVoice3 WSL2 service from Windows and run a smoke TTS test.

This script is intentionally Windows-side only. It opens a visible Windows
Terminal tab (or a separate WSL console window), starts Ubuntu + uvicorn there,
then keeps this Python process free to poll /health, call /v1/tts, save the WAV
under the Windows temporary directory, and play it.
"""

import argparse
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
DEFAULT_HEALTH_URL = f"http://127.0.0.1:{DEFAULT_PORT}/health"
DEFAULT_TTS_URL = f"http://127.0.0.1:{DEFAULT_PORT}/v1/tts"
DEFAULT_SERVICE_DIR = "~/sylphos_services/cosyvoice3"
DEFAULT_TEST_TEXT = "你好，Sylphos。CosyVoice3 服务启动成功。"
DEFAULT_WSL_PID_FILE = "/tmp/sylphos_cosyvoice3_uvicorn.pid"

WSL_ENVIRONMENT = {
    "COSYVOICE_REPO": "/home/shakamilo/CosyVoice",
    "COSYVOICE_MODEL_PATH": "/home/shakamilo/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B",
    "COSYVOICE_RL_MODEL_PATH": "/home/shakamilo/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl",
    "COSYVOICE_PROMPT_DIR": "/home/shakamilo/sylphos_services/cosyvoice3/prompts",
}


def build_wsl_start_script(
    *,
    conda_env: str,
    service_dir: str,
    host: str,
    port: int,
    distro: str,
    pid_file: str = DEFAULT_WSL_PID_FILE,
    extra_env: dict[str, str] | None = None,
) -> str:
    """Return the bash script executed inside the new WSL2 Ubuntu window."""

    env = {**WSL_ENVIRONMENT, **(extra_env or {})}
    exports = "\n".join(f"export {name}={shell_quote(value)}" for name, value in env.items())
    return f"""set -Eeuo pipefail

echo "[CosyVoice3] WSL distro: $(cat /etc/os-release 2>/dev/null | sed -n 's/^PRETTY_NAME=//p' | tr -d '\"' || true)"
echo "[CosyVoice3] Shell PID: $$"
echo "[CosyVoice3] After exec, uvicorn PID will be: $$"
echo "$$" > {shell_quote(pid_file)}
echo "[CosyVoice3] Stop service: press Ctrl+C in this window, or from Windows run: wsl -d {shell_quote(distro)} -- kill $$"

if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  . "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  . "$HOME/anaconda3/etc/profile.d/conda.sh"
elif command -v conda >/dev/null 2>&1; then
  . "$(conda info --base)/etc/profile.d/conda.sh"
else
  echo "[CosyVoice3] ERROR: conda not found. Install Miniconda/Anaconda in WSL2 first." >&2
  exec bash
fi

conda activate {shell_quote(conda_env)}
{exports}
cd {shell_quote(service_dir)}

echo "[CosyVoice3] Conda env: {conda_env}"
echo "[CosyVoice3] Service dir: $(pwd)"
echo "[CosyVoice3] COSYVOICE_REPO=$COSYVOICE_REPO"
echo "[CosyVoice3] COSYVOICE_MODEL_PATH=$COSYVOICE_MODEL_PATH"
echo "[CosyVoice3] COSYVOICE_RL_MODEL_PATH=$COSYVOICE_RL_MODEL_PATH"
echo "[CosyVoice3] COSYVOICE_PROMPT_DIR=$COSYVOICE_PROMPT_DIR"
echo "[CosyVoice3] Starting uvicorn on {host}:{port}; logs remain visible in this window."
exec uvicorn cosyvoice_server:app --host {shell_quote(host)} --port {port}
"""


def shell_quote(value: str) -> str:
    """Quote a value for POSIX shell usage inside WSL."""

    return "'" + value.replace("'", "'\"'\"'") + "'"


def launch_service_window(args: argparse.Namespace) -> subprocess.Popen[Any]:
    """Open Windows Terminal or a separate WSL console and start uvicorn."""

    bash_script = build_wsl_start_script(
        conda_env=args.conda_env,
        service_dir=args.service_dir,
        host=args.host,
        port=args.port,
        distro=args.distro,
    )
    wsl_command = ["wsl.exe", "-d", args.distro, "--", "bash", "-lc", bash_script]

    terminal = args.terminal
    if terminal == "auto":
        terminal = "wt" if shutil.which("wt.exe") else "wsl"

    if terminal == "wt":
        if not shutil.which("wt.exe"):
            raise RuntimeError("wt.exe was requested but Windows Terminal was not found on PATH.")
        command = ["wt.exe", "new-tab", "--title", "CosyVoice3 uvicorn", *wsl_command]
        print("[Windows] Opening Windows Terminal tab for CosyVoice3 uvicorn logs...")
        return subprocess.Popen(command)

    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    print("[Windows] Opening a separate WSL console window for CosyVoice3 uvicorn logs...")
    return subprocess.Popen(wsl_command, creationflags=creationflags)


def read_wsl_uvicorn_pid(distro: str, pid_file: str = DEFAULT_WSL_PID_FILE) -> str | None:
    """Best-effort read of the uvicorn PID file written in the WSL service window."""

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


def wait_for_health(health_url: str, timeout_seconds: float, poll_interval: float) -> dict[str, Any]:
    """Poll /health until it reports ok=true or timeout expires."""

    deadline = time.monotonic() + timeout_seconds
    last_error = "health endpoint was not contacted"
    attempt = 0

    while time.monotonic() < deadline:
        attempt += 1
        try:
            with request.urlopen(health_url, timeout=min(10.0, poll_interval + 2.0)) as response:
                body = response.read().decode("utf-8", errors="replace")
                payload = json.loads(body)
                if payload.get("ok") is True:
                    print(f"[Windows] Health check passed on attempt {attempt}: {health_url}")
                    return payload
                errors = payload.get("errors") or []
                last_error = f"health returned ok={payload.get('ok')!r}; errors={errors!r}"
        except error.HTTPError as exc:
            last_error = f"HTTP {exc.code}: {exc.reason}"
        except error.URLError as exc:
            last_error = f"connection not ready: {exc.reason}"
        except TimeoutError:
            last_error = "health request timed out"
        except json.JSONDecodeError as exc:
            last_error = f"health returned invalid JSON: {exc}"
        except OSError as exc:
            last_error = str(exc)

        remaining = max(0.0, deadline - time.monotonic())
        print(f"[Windows] Waiting for CosyVoice3 health... {last_error}; remaining {remaining:.0f}s")
        time.sleep(poll_interval)

    raise TimeoutError(f"CosyVoice3 did not become healthy within {timeout_seconds:.0f}s: {last_error}")


def synthesize_test_wav(
    *,
    tts_url: str,
    text: str,
    voice_id: str,
    prompt_wav: str | None,
    prompt_text: str | None,
    model_version: str,
    timeout_seconds: float,
) -> Path:
    """Call /v1/tts and save the returned WAV to the Windows temp directory."""

    payload: dict[str, Any] = {
        "text": text,
        "voice_id": voice_id,
        "model_version": model_version,
    }
    if prompt_wav:
        payload["prompt_wav"] = prompt_wav
    if prompt_text is not None:
        payload["prompt_text"] = prompt_text

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        tts_url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "audio/wav, application/json"},
        method="POST",
    )

    print(f"[Windows] Calling TTS endpoint: {tts_url}")
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else exc.reason
        raise RuntimeError(f"TTS request failed with HTTP {exc.code}: {detail}") from exc

    wav_bytes = extract_wav_bytes(response_body, content_type)
    wav_path = Path(tempfile.gettempdir()) / f"cosyvoice3_test_{int(time.time())}_{uuid.uuid4().hex[:8]}.wav"
    wav_path.write_bytes(wav_bytes)
    print(f"[Windows] Saved test WAV: {wav_path}")
    return wav_path


def extract_wav_bytes(response_body: bytes, content_type: str) -> bytes:
    """Accept direct audio/wav responses or compatible JSON base64 responses."""

    media_type = content_type.split(";", 1)[0].strip().lower()
    if response_body.startswith(b"RIFF") and response_body[8:12] == b"WAVE":
        return response_body

    if media_type == "application/json" or response_body.lstrip().startswith(b"{"):
        payload = json.loads(response_body.decode("utf-8"))
        if payload.get("ok") is False:
            raise RuntimeError(f"TTS API returned an error: {payload}")
        import base64

        for key in ("wav_base64", "audio_base64", "audio", "data"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                raw = value.split(",", 1)[1] if value.startswith("data:") and "," in value else value
                decoded = base64.b64decode(raw)
                if decoded.startswith(b"RIFF") and decoded[8:12] == b"WAVE":
                    return decoded

    raise RuntimeError(f"TTS API did not return WAV audio. Content-Type={content_type!r}")


def play_wav(path: Path, backend: str) -> None:
    """Play the WAV with winsound or the Windows default associated player."""

    if backend in {"auto", "winsound"}:
        import winsound

        try:
            print(f"[Windows] Playing with winsound: {path}")
            winsound.PlaySound(str(path), winsound.SND_FILENAME)
            return
        except Exception:
            if backend == "winsound":
                raise
            print("[Windows] winsound playback failed; falling back to default player.")

    print(f"[Windows] Opening with default player: {path}")
    os.startfile(str(path))  # type: ignore[attr-defined]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start CosyVoice3 in a visible WSL2 Ubuntu window, wait for health, run a test TTS, and play it.",
    )
    parser.add_argument("--distro", default=DEFAULT_DISTRIBUTION, help="WSL distribution name, e.g. Ubuntu or Ubuntu-24.04.")
    parser.add_argument("--terminal", choices=["auto", "wt", "wsl"], default="auto", help="Use Windows Terminal or a standalone WSL console.")
    parser.add_argument("--no-launch", action="store_true", help="Do not start a new service window; only poll and test an existing service.")
    parser.add_argument("--conda-env", default=DEFAULT_CONDA_ENV, help="Conda environment to activate inside WSL.")
    parser.add_argument("--service-dir", default=DEFAULT_SERVICE_DIR, help="CosyVoice3 service directory inside WSL.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="uvicorn host inside WSL.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="uvicorn port exposed to Windows localhost.")
    parser.add_argument("--health-url", default=None, help="Override health URL. Defaults to http://127.0.0.1:<port>/health.")
    parser.add_argument("--tts-url", default=None, help="Override TTS URL. Defaults to http://127.0.0.1:<port>/v1/tts.")
    parser.add_argument("--timeout", type=float, default=300.0, help="Seconds to wait for health and for the TTS request.")
    parser.add_argument("--poll-interval", type=float, default=5.0, help="Seconds between health checks.")
    parser.add_argument("--text", default=DEFAULT_TEST_TEXT, help="Short test text to synthesize.")
    parser.add_argument("--voice-id", default="official", help="voice_id sent to /v1/tts; defaults to official.")
    parser.add_argument("--prompt-wav", default=None, help="Optional WSL/Linux prompt WAV path for future zero-shot tests.")
    parser.add_argument("--prompt-text", default=None, help="Optional prompt transcript for future zero-shot tests.")
    parser.add_argument("--model-version", choices=["base", "rl"], default="base", help="CosyVoice model version.")
    parser.add_argument("--play-backend", choices=["auto", "winsound", "default_app"], default="auto", help="Audio playback backend.")
    return parser.parse_args()


def main() -> int:
    if platform.system() != "Windows":
        print("ERROR: This script is intended to be run by Windows Python, not inside WSL/Linux.", file=sys.stderr)
        return 2

    args = parse_args()
    health_url = args.health_url or f"http://127.0.0.1:{args.port}/health"
    tts_url = args.tts_url or f"http://127.0.0.1:{args.port}/v1/tts"

    process: subprocess.Popen[Any] | None = None
    if not args.no_launch:
        process = launch_service_window(args)
        print(f"[Windows] Launcher process PID: {process.pid}")
        time.sleep(1.0)
        uvicorn_pid = read_wsl_uvicorn_pid(args.distro)
        if uvicorn_pid:
            print(f"[Windows] Uvicorn PID inside WSL: {uvicorn_pid}")
            print(f"[Windows] Stop command: wsl -d {args.distro} -- kill {uvicorn_pid}")
        else:
            print("[Windows] Uvicorn PID will be printed inside the CosyVoice3 WSL window.")

    print("[Windows] To stop CosyVoice3: press Ctrl+C in the service window, or run the printed WSL kill command.")
    health_payload = wait_for_health(health_url, args.timeout, args.poll_interval)
    print(f"[Windows] Service health OK: {json.dumps(health_payload, ensure_ascii=False, indent=2)}")

    wav_path = synthesize_test_wav(
        tts_url=tts_url,
        text=args.text,
        voice_id=args.voice_id,
        prompt_wav=args.prompt_wav,
        prompt_text=args.prompt_text,
        model_version=args.model_version,
        timeout_seconds=args.timeout,
    )
    play_wav(wav_path, args.play_backend)
    print("[Windows] Smoke test completed successfully.")
    print(f"[Windows] WAV file remains available at: {wav_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
