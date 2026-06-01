from __future__ import annotations

"""CosyVoice TTS engine adapter.

The adapter intentionally keeps the public Sylphos interface small while
wrapping the CosyVoice project API behind a stable `synthesize_to_file()`
method.  CosyVoice is commonly installed from source, so imports are delayed
until model construction and all dependency failures include the Sylphos TTS
requirements hint.
"""

import importlib
import inspect
import wave
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .base import TTSResult

_INSTALL_HINT = (
    "缺少 TTS / CosyVoice 依赖。请先运行：pip install -r requirements-tts.txt。"
    "如果 CosyVoice 未发布到 PyPI，请按 docs/tts_cosyvoice.md 从源码安装 CosyVoice。"
)
_MODEL_LOAD_HINT = (
    "CosyVoice 模型加载失败。可能原因：\n"
    "1) 模型未下载或远程模型名不可访问；\n"
    "2) 网络问题导致 ModelScope / HuggingFace 下载失败；\n"
    "3) Python 3.12 / Torch / torchaudio / CUDA 版本不兼容；\n"
    "4) 本地模型目录路径错误或缺少配置文件。"
)
_DEFAULT_MODEL = "iic/CosyVoice3-0.5B"
_DEFAULT_SAMPLE_RATE = 22050


class CosyVoiceEngine:
    """Sylphos official CosyVoice TTS implementation.

    Args:
        model: Remote model id or local model directory.  The default targets a
            CosyVoice3 model name and can be overridden for local deployments.
        device: Inference device.  The formal engine defaults to ``"gpu"``;
            healthcheck defaults to CPU for safer first-run validation.
        sample_rate: Fallback sample rate used when CosyVoice output does not
            carry one explicitly.
        load_jit/load_trt/load_vllm/fp16: Reserved CosyVoice runtime knobs kept
            configurable without forcing the public API to grow later.
    """

    def __init__(
        self,
        model: str | Path = _DEFAULT_MODEL,
        device: str = "gpu",
        sample_rate: int = _DEFAULT_SAMPLE_RATE,
        load_jit: bool = False,
        load_trt: bool = False,
        load_vllm: bool = False,
        fp16: bool | None = None,
        **model_kwargs: Any,
    ) -> None:
        self.model = str(model)
        self.device = device
        self.sample_rate = sample_rate
        self.load_jit = load_jit
        self.load_trt = load_trt
        self.load_vllm = load_vllm
        self.fp16 = fp16
        self.model_kwargs = model_kwargs
        self._engine: Any | None = None

        # 关键节点：模型在构造阶段加载/下载，便于 --download-only 只初始化模型缓存。
        self._engine = self._build_model()

    def _build_model(self) -> Any:
        engine_class = self._import_cosyvoice_class()
        kwargs: dict[str, Any] = {
            "model_dir": self.model,
            "device": self.device,
            "load_jit": self.load_jit,
            "load_trt": self.load_trt,
            "load_vllm": self.load_vllm,
            **self.model_kwargs,
        }
        if self.fp16 is not None:
            kwargs["fp16"] = self.fp16

        try:
            # CosyVoice class signatures have changed between releases.  Filter
            # kwargs when the constructor exposes a concrete signature so this
            # adapter can work with CosyVoice3/CosyVoice2/source installs.
            init_signature = inspect.signature(engine_class)
            accepts_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in init_signature.parameters.values()
            )
            if not accepts_kwargs:
                kwargs = {key: value for key, value in kwargs.items() if key in init_signature.parameters}
            return engine_class(**kwargs)
        except Exception as exc:  # pragma: no cover - depends on model runtime
            raise RuntimeError(_MODEL_LOAD_HINT) from exc

    def _import_cosyvoice_class(self) -> type[Any]:
        try:
            module = importlib.import_module("cosyvoice.cli.cosyvoice")
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(_INSTALL_HINT) from exc

        # 优先 CosyVoice3，兼容当前源码仓库中可能存在的 CosyVoice2/CosyVoice 类。
        for class_name in ("CosyVoice3", "CosyVoice2", "CosyVoice"):
            candidate = getattr(module, class_name, None)
            if candidate is not None:
                return candidate
        raise RuntimeError("CosyVoice 安装中未找到 CosyVoice3 / CosyVoice2 / CosyVoice 类。" + _INSTALL_HINT)

    def synthesize_to_file(
        self,
        text: str,
        output_path: str | Path,
        **kwargs: Any,
    ) -> TTSResult:
        """Synthesize text and write a WAV file.

        ``speaker``, ``prompt_wav`` and ``prompt_text`` are accepted as reserved
        parameters.  The method maps them to CosyVoice calls only when supplied,
        keeping the default text-to-speech path simple and predictable.
        """
        if self._engine is None:
            raise RuntimeError("CosyVoice engine is closed.")
        if not text or not text.strip():
            raise ValueError("TTS text must not be empty.")

        output = Path(output_path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        speaker = kwargs.pop("speaker", None) or kwargs.pop("voice", None)
        prompt_wav = kwargs.pop("prompt_wav", None)
        prompt_text = kwargs.pop("prompt_text", "")

        # 关键节点：仅在这里调用 CosyVoice 推理接口，Runtime handler 只依赖统一工厂。
        generated = self._synthesize(text=text, speaker=speaker, prompt_wav=prompt_wav, prompt_text=prompt_text, **kwargs)
        audio, sample_rate, raw_item = self._extract_audio(generated)

        # 关键节点：统一输出 WAV 文件，避免上层关心 CosyVoice 返回 tensor/ndarray/list 的差异。
        self._write_wav(output, audio=audio, sample_rate=sample_rate)

        return TTSResult(
            text=text,
            audio_path=output,
            sample_rate=sample_rate,
            provider="cosyvoice",
            metadata={
                "model": self.model,
                "device": self.device,
                "speaker": speaker,
                "prompt_wav": str(prompt_wav) if prompt_wav else None,
                "prompt_text": prompt_text or None,
                "raw_keys": sorted(raw_item.keys()) if isinstance(raw_item, dict) else None,
            },
        )

    def _synthesize(self, *, text: str, speaker: str | None, prompt_wav: Any, prompt_text: str, **kwargs: Any) -> Any:
        if prompt_wav:
            call = getattr(self._engine, "inference_zero_shot", None)
            if call is None:
                raise RuntimeError("当前 CosyVoice 版本不支持 prompt_wav / zero-shot 合成。")
            return call(text, prompt_text, str(prompt_wav), **kwargs)

        if speaker:
            call = getattr(self._engine, "inference_sft", None)
            if call is not None:
                return call(text, speaker, **kwargs)

        call = getattr(self._engine, "inference_instruct2", None) or getattr(self._engine, "inference_instruct", None)
        if call is not None and speaker:
            return call(text, speaker, "", **kwargs)

        call = getattr(self._engine, "inference_sft", None)
        if call is not None:
            voice = speaker or kwargs.pop("default_spk", "中文女")
            return call(text, voice, **kwargs)

        call = getattr(self._engine, "inference", None) or getattr(self._engine, "generate", None)
        if call is None:
            raise RuntimeError("当前 CosyVoice 引擎未暴露可用的文本转语音推理接口。")
        return call(text, **kwargs)

    def _extract_audio(self, generated: Any) -> tuple[Any, int, Any]:
        item = self._first_generated_item(generated)
        sample_rate = self.sample_rate
        audio = item

        if isinstance(item, dict):
            for key in ("tts_speech", "speech", "audio", "wav"):
                if key in item and item[key] is not None:
                    audio = item[key]
                    break
            sample_rate_value = item.get("sample_rate") or item.get("sampling_rate") or item.get("sr")
            sample_rate = int(sample_rate_value or sample_rate)

        if audio is None:
            raise RuntimeError("CosyVoice 未返回可写入的音频数据。")
        return audio, sample_rate, item

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
        try:
            import torchaudio
            import torch
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(_INSTALL_HINT) from exc

        if isinstance(audio, (str, Path)):
            source = Path(audio).expanduser().resolve()
            if not source.exists():
                raise FileNotFoundError(f"CosyVoice 返回的音频文件不存在: {source}")
            output.write_bytes(source.read_bytes())
            return

        if isinstance(audio, (bytes, bytearray)):
            output.write_bytes(bytes(audio))
            return

        tensor = torch.as_tensor(audio).detach().cpu()
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        elif tensor.ndim > 2:
            tensor = tensor.reshape(1, -1)
        elif tensor.shape[0] > tensor.shape[-1]:
            tensor = tensor.transpose(0, 1)

        tensor = tensor.to(dtype=torch.float32)
        try:
            torchaudio.save(str(output), tensor, sample_rate=sample_rate, format="wav")
        except Exception:
            # torchaudio may lack a backend on minimal systems.  Fall back to
            # the stdlib wave writer for mono/stereo float tensors.
            self._write_wav_stdlib(output, tensor=tensor, sample_rate=sample_rate)

    def _write_wav_stdlib(self, output: Path, *, tensor: Any, sample_rate: int) -> None:
        import numpy as np

        array = tensor.numpy()
        if array.ndim == 2:
            array = array.T
        clipped = np.clip(array, -1.0, 1.0)
        pcm16 = (clipped * 32767.0).astype("<i2")
        channels = 1 if pcm16.ndim == 1 else pcm16.shape[1]
        with wave.open(str(output), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())

    def close(self) -> None:
        """Release the model reference while preserving the formal interface."""
        self._engine = None
