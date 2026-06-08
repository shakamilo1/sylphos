from __future__ import annotations

"""FastAPI service template for running CosyVoice3 from WSL2.

The script is intentionally self-contained enough to run either from this
repository path or after being copied to ``~/sylphos_services/cosyvoice3``.  It
prefers Sylphos' ``CosyVoiceEngine`` adapter when available, and falls back to a
small direct CosyVoice wrapper when the Sylphos package is not importable from a
copied deployment directory.
"""

import base64
import importlib
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
from pydantic import BaseModel, Field

SERVICE_NAME = "cosyvoice3"
DEFAULT_MODEL_PATH = "~/sylphos_models/Fun-CosyVoice3-0.5B"
DEFAULT_DEVICE = "cuda"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 9880
DEFAULT_OUTPUT_PATH = "~/sylphos_outputs/tts/latest_tts.wav"
DEFAULT_SAMPLE_RATE = 22050


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def _model_path() -> str:
    return str(Path(_env("COSYVOICE_MODEL_PATH", DEFAULT_MODEL_PATH)).expanduser())


def _device() -> str:
    return _env("COSYVOICE_DEVICE", DEFAULT_DEVICE)


def _default_output_path() -> Path:
    return Path(DEFAULT_OUTPUT_PATH).expanduser()


class TTSRequest(BaseModel):
    text: str = Field(..., description="Text to synthesize.")
    output_path: str | None = Field(default=None, description="Destination WAV path inside WSL2/Linux.")
    prompt_wav: str | None = Field(default=None, description="Optional zero-shot prompt WAV path.")
    prompt_text: str | None = Field(default=None, description="Text transcript for prompt_wav.")
    speaker: str | None = Field(default=None, description="Optional speaker/voice name for SFT-capable models.")
    model_version: str | None = Field(default=None, description="Accepted for Windows client compatibility; not used by this template.")


class DirectCosyVoiceRuntime:
    """Minimal direct CosyVoice wrapper used when Sylphos is not importable."""

    def __init__(self, model_path: str, device: str) -> None:
        self.model_path = model_path
        self.device = device
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._engine = self._build_model()

    def _build_model(self) -> Any:
        if not _module_exists("cosyvoice.cli.cosyvoice"):
            raise RuntimeError(
                "CosyVoice package is not importable. Install CosyVoice from its official source repository "
                "in the same WSL2 Python environment; requirements-tts.txt does not include CosyVoice itself."
            )
        module = importlib.import_module("cosyvoice.cli.cosyvoice")

        for class_name in ("CosyVoice3", "CosyVoice2", "CosyVoice"):
            engine_class = getattr(module, class_name, None)
            if engine_class is not None:
                break
        else:
            raise RuntimeError("CosyVoice install does not expose CosyVoice3, CosyVoice2, or CosyVoice.")

        kwargs: dict[str, Any] = {
            "model_dir": self.model_path,
            "device": self.device,
            "load_jit": False,
            "load_trt": False,
            "load_vllm": False,
        }
        init_signature = inspect.signature(engine_class)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in init_signature.parameters.values())
        if not accepts_kwargs:
            kwargs = {key: value for key, value in kwargs.items() if key in init_signature.parameters}
        return engine_class(**kwargs)

    def synthesize_to_file(self, text: str, output_path: str | Path, **kwargs: Any) -> Any:
        if not text or not text.strip():
            raise ValueError("TTS text must not be empty.")

        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        prompt_wav = kwargs.pop("prompt_wav", None)
        prompt_text = kwargs.pop("prompt_text", "") or ""
        speaker = kwargs.pop("speaker", None) or kwargs.pop("voice", None)
        generated = self._synthesize(text=text.strip(), prompt_wav=prompt_wav, prompt_text=prompt_text, speaker=speaker, **kwargs)
        audio, sample_rate = self._extract_audio(generated)
        self._write_wav(output, audio=audio, sample_rate=sample_rate)
        return output

    def _synthesize(self, *, text: str, prompt_wav: Any, prompt_text: str, speaker: str | None, **kwargs: Any) -> Any:
        if prompt_wav:
            call = getattr(self._engine, "inference_zero_shot", None)
            if call is None:
                raise RuntimeError("This CosyVoice runtime does not support prompt_wav / zero-shot synthesis.")
            return call(text, prompt_text, str(prompt_wav), **kwargs)

        if speaker:
            call = getattr(self._engine, "inference_sft", None)
            if call is not None:
                return call(text, speaker, **kwargs)
            call = getattr(self._engine, "inference_instruct2", None) or getattr(self._engine, "inference_instruct", None)
            if call is not None:
                return call(text, speaker, "", **kwargs)

        call = getattr(self._engine, "inference_sft", None)
        if call is not None:
            return call(text, speaker or "中文女", **kwargs)

        call = getattr(self._engine, "inference", None) or getattr(self._engine, "generate", None)
        if call is None:
            raise RuntimeError("CosyVoice runtime does not expose a usable text-to-speech method.")
        return call(text, **kwargs)

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


_engine: Any | None = None
_engine_errors: list[str] = []
_engine_lock = Lock()


def _create_runtime() -> Any:
    model_path = _model_path()
    device = _device()
    sylphos_error: Exception | str = "Sylphos adapter is not importable from the current Python path."

    if _module_exists("sylphos.voice.tts.cosyvoice"):
        sylphos_cosyvoice = importlib.import_module("sylphos.voice.tts.cosyvoice")
        engine_class = getattr(sylphos_cosyvoice, "CosyVoiceEngine")
        try:
            return engine_class(model=model_path, device=device)
        except Exception as exc:
            sylphos_error = exc

    try:
        return DirectCosyVoiceRuntime(model_path=model_path, device=device)
    except Exception as direct_exc:
        raise RuntimeError(
            "Failed to load CosyVoice through the Sylphos adapter or direct CosyVoice API. "
            f"Sylphos adapter error: {sylphos_error}. Direct CosyVoice error: {direct_exc}."
        ) from direct_exc


def _get_runtime() -> tuple[Any | None, list[str]]:
    global _engine
    with _engine_lock:
        if _engine is not None:
            return _engine, list(_engine_errors)
        try:
            _engine = _create_runtime()
            _engine_errors.clear()
        except Exception as exc:
            _engine_errors[:] = [str(exc)]
            return None, list(_engine_errors)
        return _engine, []


def _health_payload() -> dict[str, Any]:
    runtime, errors = _get_runtime()
    loaded = runtime is not None
    return {
        "ok": loaded,
        "service": SERVICE_NAME,
        "model_path": _model_path(),
        "device": _device(),
        "python": sys.version.split()[0],
        "cosyvoice_loaded": loaded,
        "errors": errors,
    }


app = FastAPI(title="Sylphos CosyVoice3 TTS Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return _health_payload()


@app.post("/tts")
def tts(request: TTSRequest) -> dict[str, Any]:
    started = time.perf_counter()
    output_path = Path(request.output_path).expanduser() if request.output_path else _default_output_path()
    errors: list[str] = []

    try:
        runtime, load_errors = _get_runtime()
        if runtime is None:
            return {
                "ok": False,
                "output_path": str(output_path),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "errors": load_errors or ["CosyVoice runtime is not loaded."],
            }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        runtime.synthesize_to_file(
            request.text,
            output_path,
            prompt_wav=request.prompt_wav,
            prompt_text=request.prompt_text,
            speaker=request.speaker,
        )
    except Exception as exc:
        errors.append(str(exc))

    payload = {
        "ok": not errors,
        "output_path": str(output_path),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "errors": errors,
    }
    if not errors and output_path.exists():
        # Allows existing Windows-side clients that expect WAV data in JSON to
        # work while still exposing the WSL2 output path requested by this API.
        payload["wav_base64"] = base64.b64encode(output_path.read_bytes()).decode("ascii")
    return payload


@app.post("/v1/tts")
def tts_v1(request: TTSRequest) -> dict[str, Any]:
    """Compatibility alias for existing Windows-side Sylphos clients."""
    return tts(request)


def main() -> None:
    uvicorn = importlib.import_module("uvicorn")
    host = _env("COSYVOICE_HOST", DEFAULT_HOST)
    port = int(_env("COSYVOICE_PORT", str(DEFAULT_PORT)))
    uvicorn.run("cosyvoice_server:app", host=host, port=port)


if __name__ == "__main__":
    main()
