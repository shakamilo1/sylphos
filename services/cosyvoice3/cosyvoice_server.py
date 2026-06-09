from __future__ import annotations

"""FastAPI service template for running CosyVoice3 from WSL2.

The script is intentionally self-contained enough to run either from this
repository path or after being copied to ``~/sylphos_services/cosyvoice3``. It
loads CosyVoice from a local official source checkout instead of assuming the
``cosyvoice`` package was installed into site-packages.
"""

import base64
import importlib
import json
import inspect
import os
import sys
import time
import wave
from collections.abc import Iterable
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel, Field

SERVICE_NAME = "cosyvoice3"
DEFAULT_COSYVOICE_REPO = "~/CosyVoice"
DEFAULT_MODEL_PATH = "~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B"
DEFAULT_RL_MODEL_PATH = "~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl"
DEFAULT_DEVICE = "cuda"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9880
DEFAULT_OUTPUT_PATH = "~/sylphos_outputs/tts/latest_tts.wav"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_PROMPT_TEXT = "You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。"
VALID_MODEL_VERSIONS = {"base", "rl"}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _expand_path(value: str) -> str:
    return str(Path(value).expanduser())


def _cosyvoice_repo() -> str:
    return _expand_path(_env("COSYVOICE_REPO", DEFAULT_COSYVOICE_REPO))


def _cosyvoice_py_path(repo: str | None = None) -> Path:
    return Path(repo or _cosyvoice_repo()).expanduser() / "cosyvoice" / "cli" / "cosyvoice.py"


def _cosyvoice_path_entries(repo: str | None = None) -> list[str]:
    root = Path(repo or _cosyvoice_repo()).expanduser()
    return [str(root), str(root / "third_party" / "Matcha-TTS")]


def _ensure_cosyvoice_repo_on_path(repo: str | None = None) -> list[str]:
    """Add the official CosyVoice checkout and Matcha-TTS folder to sys.path."""

    added: list[str] = []
    for entry in reversed(_cosyvoice_path_entries(repo)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
            added.append(entry)
    return added


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _model_path() -> str:
    return _expand_path(_env("COSYVOICE_MODEL_PATH", DEFAULT_MODEL_PATH))


def _rl_model_path() -> str:
    return _expand_path(_env("COSYVOICE_RL_MODEL_PATH", DEFAULT_RL_MODEL_PATH))


def _model_path_for_version(model_version: str | None) -> str:
    version = (model_version or "base").strip().lower()
    if version == "base":
        return _model_path()
    if version == "rl":
        return _rl_model_path()
    raise ValueError("model_version must be 'base' or 'rl'.")


def _device() -> str:
    return _env("COSYVOICE_DEVICE", DEFAULT_DEVICE)


def _default_output_path() -> Path:
    return Path(DEFAULT_OUTPUT_PATH).expanduser()


def _default_prompt_wav_path() -> Path:
    return Path(_cosyvoice_repo()).expanduser() / "asset" / "zero_shot_prompt.wav"


def _default_prompt_text() -> str:
    return _env("COSYVOICE_PROMPT_TEXT", DEFAULT_PROMPT_TEXT)


def _format_synthesis_error(exc: Exception) -> str:
    if isinstance(exc, KeyError) and exc.args:
        speaker = str(exc.args[0])
        return f"Unsupported speaker {speaker!r} for current model; use zero-shot prompt_wav/prompt_text instead."
    return str(exc)


def _cosyvoice_importable() -> bool:
    _ensure_cosyvoice_repo_on_path()
    return _module_exists("cosyvoice.cli.cosyvoice")


def _preflight_errors(*, model_path: str | None = None, check_rl_model: bool = False) -> list[str]:
    repo = _cosyvoice_repo()
    _ensure_cosyvoice_repo_on_path(repo)
    errors: list[str] = []

    cosyvoice_py = _cosyvoice_py_path(repo)
    if not cosyvoice_py.is_file():
        errors.append(
            "CosyVoice package is not importable because the expected source file does not exist: "
            f"{cosyvoice_py}. Set COSYVOICE_REPO to the official CosyVoice checkout. Current sys.path: {sys.path}"
        )
    elif not _module_exists("cosyvoice.cli.cosyvoice"):
        errors.append(
            "CosyVoice package is not importable even after adding COSYVOICE_REPO to sys.path. "
            f"Expected source file exists: {cosyvoice_py}. Current sys.path: {sys.path}"
        )

    selected_model_path = Path(model_path or _model_path()).expanduser()
    if not selected_model_path.is_dir():
        errors.append(
            "CosyVoice model path does not exist or is not a directory: "
            f"{selected_model_path}. Set COSYVOICE_MODEL_PATH to the full model directory, for example "
            "/home/shakamilo/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B."
        )

    if check_rl_model:
        rl_path = Path(_rl_model_path()).expanduser()
        if not rl_path.is_dir():
            errors.append(
                "CosyVoice RL model path does not exist or is not a directory: "
                f"{rl_path}. Set COSYVOICE_RL_MODEL_PATH to the full RL model directory."
            )
    return errors


_ensure_cosyvoice_repo_on_path()


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    output_path: str | None = Field(default=None, description="Destination WAV path inside WSL2/Linux.")
    prompt_wav: str | None = Field(default=None, description="Optional zero-shot prompt WAV path.")
    prompt_text: str | None = Field(default=None, description="Text transcript for prompt_wav.")
    speaker: str | None = Field(default=None, description="Optional speaker/voice name for SFT-capable models.")
    model_version: str = Field(default="base", description="CosyVoice3 model version: 'base' or 'rl'.")


class DirectCosyVoiceRuntime:
    """Minimal direct CosyVoice wrapper loaded from the official source repo."""

    def __init__(self, model_path: str, device: str | None = None) -> None:
        self.model_path = model_path
        # COSYVOICE_DEVICE is reported in /health for diagnostics, but is not
        # passed into official CosyVoice constructors unless their signatures
        # explicitly add support for it in the future.
        self.device = device
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._engine = self._build_model()

    def _build_model(self) -> Any:
        _ensure_cosyvoice_repo_on_path()
        if not _module_exists("cosyvoice.cli.cosyvoice"):
            raise RuntimeError(
                "CosyVoice package is not importable. Set COSYVOICE_REPO to the official source checkout; "
                f"expected {_cosyvoice_py_path()} to exist. Current sys.path: {sys.path}"
            )
        try:
            module = importlib.import_module("cosyvoice.cli.cosyvoice")
        except Exception as exc:
            raise RuntimeError(
                "CosyVoice package is not importable even though the source path was configured. "
                f"Expected source file: {_cosyvoice_py_path()} (exists={_cosyvoice_py_path().is_file()}). "
                f"Current sys.path: {sys.path}. Import error: {exc}"
            ) from exc

        for class_name in ("AutoModel", "CosyVoice3", "CosyVoice2", "CosyVoice"):
            engine_class = getattr(module, class_name, None)
            if engine_class is not None:
                break
        else:
            raise RuntimeError("CosyVoice install does not expose AutoModel, CosyVoice3, CosyVoice2, or CosyVoice.")

        # Match the verified minimal CosyVoice3 invocation as closely as
        # possible: AutoModel(model_dir="...").  In particular, do not pass
        # device=... into AutoModel/CosyVoice3/CosyVoice2/CosyVoice just because
        # COSYVOICE_DEVICE exists for health diagnostics.
        kwargs: dict[str, Any] = {"model_dir": self.model_path}
        try:
            init_signature = inspect.signature(engine_class)
        except (TypeError, ValueError):
            return engine_class(**kwargs)

        parameters = init_signature.parameters
        if "model_dir" in parameters or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
            if "device" in parameters:
                kwargs["device"] = self.device
            return engine_class(**kwargs)
        return engine_class(self.model_path)

    def synthesize_to_file(self, text: str, output_path: str | Path, **kwargs: Any) -> Any:
        if not text or not text.strip():
            raise ValueError("TTS text must not be empty.")

        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        prompt_wav = kwargs.pop("prompt_wav", None)
        if prompt_wav is None:
            prompt_wav = str(_default_prompt_wav_path())
        prompt_text = kwargs.pop("prompt_text", None)
        if prompt_text is None:
            prompt_text = _default_prompt_text()
        speaker = kwargs.pop("speaker", None) or kwargs.pop("voice", None)
        generated = self._synthesize(text=text.strip(), prompt_wav=prompt_wav, prompt_text=prompt_text, speaker=speaker, **kwargs)
        audio, sample_rate = self._extract_audio(generated)
        self._write_wav(output, audio=audio, sample_rate=sample_rate)
        return output

    def _synthesize(self, *, text: str, prompt_wav: Any, prompt_text: str, speaker: str | None, **kwargs: Any) -> Any:
        if speaker:
            try:
                call = getattr(self._engine, "inference_sft", None)
                if call is not None:
                    return call(text, speaker, **kwargs)
                call = getattr(self._engine, "inference_instruct2", None) or getattr(self._engine, "inference_instruct", None)
                if call is not None:
                    return call(text, speaker, "", **kwargs)
            except KeyError as exc:
                raise RuntimeError(_format_synthesis_error(exc)) from exc
            raise RuntimeError(f"Unsupported speaker {speaker!r} for current model; use zero-shot prompt_wav/prompt_text instead.")

        call = getattr(self._engine, "inference_zero_shot", None)
        if call is None:
            raise RuntimeError("This CosyVoice runtime does not support zero-shot synthesis; provide a model with inference_zero_shot.")
        kwargs.setdefault("stream", False)
        return call(text, prompt_text, str(prompt_wav), **kwargs)

    def _extract_audio(self, generated: Any) -> tuple[Any, int]:
        item = self._first_generated_item(generated)
        audio = item
        sample_rate = self.sample_rate
        if isinstance(item, dict):
            for key in ("tts_speech", "speech", "audio", "wav"):
                if item.get(key) is not None:
                    audio = item[key]
                    break
            sample_rate = int(item.get("sample_rate") or item.get("sampling_rate") or item.get("sr") or sample_rate)
        if audio is None:
            raise RuntimeError("CosyVoice did not return writable audio data.")
        return audio, sample_rate

    def _first_generated_item(self, generated: Any) -> Any:
        if isinstance(generated, dict):
            return generated
        if isinstance(generated, (str, bytes, bytearray)):
            return generated
        if isinstance(generated, Iterable):
            for item in generated:
                return item
        return generated

    def _write_wav(self, output: Path, *, audio: Any, sample_rate: int) -> None:
        if isinstance(audio, (str, Path)):
            source = Path(audio).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError(f"CosyVoice returned an audio path that does not exist: {source}")
            output.write_bytes(source.read_bytes())
            return
        if isinstance(audio, (bytes, bytearray)):
            output.write_bytes(bytes(audio))
            return

        torch = importlib.import_module("torch")
        tensor = torch.as_tensor(audio).detach().cpu()
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.ndim > 2:
            tensor = tensor.reshape(1, -1)
        elif tensor.shape[0] > tensor.shape[-1]:
            tensor = tensor.transpose(0, 1)
        tensor = tensor.to(dtype=torch.float32)

        if not _module_exists("torchaudio"):
            self._write_wav_stdlib(output, tensor=tensor, sample_rate=sample_rate)
            return

        torchaudio = importlib.import_module("torchaudio")
        try:
            torchaudio.save(str(output), tensor, sample_rate=sample_rate, format="wav")
        except Exception:
            self._write_wav_stdlib(output, tensor=tensor, sample_rate=sample_rate)

    def _write_wav_stdlib(self, output: Path, *, tensor: Any, sample_rate: int) -> None:
        numpy = importlib.import_module("numpy")
        array = tensor.numpy()
        if array.ndim == 2:
            array = array.T
        clipped = numpy.clip(array, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype("<i2")
        channels = 1 if pcm16.ndim == 1 else pcm16.shape[1]
        with wave.open(str(output), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())


_engines: dict[str, Any] = {}
_engine_errors: dict[str, list[str]] = {}
_engine_lock = Lock()
# Backward-compatible test hooks for older tests in this repository.
_engine: Any | None = None


def _create_runtime(model_version: str | None = "base") -> Any:
    version = (model_version or "base").strip().lower()
    if version not in VALID_MODEL_VERSIONS:
        raise ValueError("model_version must be 'base' or 'rl'.")

    model_path = _model_path_for_version(version)
    preflight = _preflight_errors(model_path=model_path, check_rl_model=False)
    if preflight:
        raise RuntimeError(" ".join(preflight))
    return DirectCosyVoiceRuntime(model_path=model_path, device=_device())


def _get_runtime(model_version: str | None = "base") -> tuple[Any | None, list[str]]:
    global _engine
    version = (model_version or "base").strip().lower()
    with _engine_lock:
        if version == "base" and _engine is not None:
            return _engine, list(_engine_errors.get(version, []))
        if version in _engines:
            return _engines[version], list(_engine_errors.get(version, []))
        try:
            runtime = _create_runtime(version)
            _engines[version] = runtime
            if version == "base":
                _engine = runtime
            _engine_errors.pop(version, None)
        except Exception as exc:
            _engine_errors[version] = [str(exc)]
            return None, list(_engine_errors[version])
        return _engines[version], []


def _reset_runtime_cache() -> None:
    global _engine
    with _engine_lock:
        _engines.clear()
        _engine_errors.clear()
        _engine = None


def _health_payload() -> dict[str, Any]:
    base_preflight_errors = _preflight_errors(model_path=_model_path(), check_rl_model=False)
    runtime, load_errors = (None, base_preflight_errors)
    if not base_preflight_errors:
        runtime, load_errors = _get_runtime("base")
    loaded = runtime is not None
    return {
        "ok": loaded,
        "service": SERVICE_NAME,
        "cosyvoice_repo": _cosyvoice_repo(),
        "model_path": _model_path(),
        "rl_model_path": _rl_model_path(),
        "device": _device(),
        "python": sys.version.split()[0],
        "cosyvoice_importable": _cosyvoice_importable(),
        "cosyvoice_loaded": loaded,
        "errors": load_errors,
    }


app = FastAPI(title="Sylphos CosyVoice3 TTS Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return _health_payload()


def _synthesize_request(request: TTSRequest) -> tuple[dict[str, Any], Path]:
    started = time.perf_counter()
    output_path = Path(request.output_path).expanduser() if request.output_path else _default_output_path()
    version = (request.model_version or "base").strip().lower()
    errors: list[str] = []
    runtime_loaded = False

    try:
        model_path = _model_path_for_version(version)
        runtime, load_errors = _get_runtime(version)
        if runtime is None:
            errors = load_errors or ["CosyVoice runtime is not loaded."]
            return {
                "ok": False,
                "error": errors[0],
                "cosyvoice_loaded": False,
                "model_version": version,
                "model_path": model_path,
                "output_path": str(output_path),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "errors": errors,
            }, output_path
        runtime_loaded = True
        output_path.parent.mkdir(parents=True, exist_ok=True)
        runtime.synthesize_to_file(
            request.text,
            output_path,
            prompt_wav=request.prompt_wav,
            prompt_text=request.prompt_text,
            speaker=request.speaker,
        )
    except Exception as exc:
        errors.append(_format_synthesis_error(exc))

    payload = {
        "ok": not errors,
        "error": errors[0] if errors else "",
        "cosyvoice_loaded": runtime_loaded,
        "model_version": version,
        "model_path": _model_path_for_version(version) if version in VALID_MODEL_VERSIONS else "",
        "output_path": str(output_path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "errors": errors,
    }
    if not errors and output_path.exists():
        payload["wav_base64"] = base64.b64encode(output_path.read_bytes()).decode("ascii")
    return payload, output_path


@app.post("/tts")
def tts(request: TTSRequest) -> dict[str, Any]:
    payload, _ = _synthesize_request(request)
    return payload


@app.post("/v1/tts")
def tts_v1(request: TTSRequest) -> Response:
    """Windows-side Sylphos compatibility endpoint returning WAV bytes."""

    payload, output_path = _synthesize_request(request)
    if payload.get("ok") and output_path.exists():
        wav_bytes = output_path.read_bytes()
        if wav_bytes.startswith(b"RIFF") and b"WAVE" in wav_bytes[:16]:
            return Response(content=wav_bytes, media_type="audio/wav")
        payload = {
            **payload,
            "ok": False,
            "error": "CosyVoice output file is not a RIFF/WAVE file.",
            "errors": ["CosyVoice output file is not a RIFF/WAVE file."],
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            status_code=500,
            media_type="application/json",
        )

    status_code = 503 if payload.get("cosyvoice_loaded") is False else 500
    return Response(
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        status_code=status_code,
        media_type="application/json",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT)
