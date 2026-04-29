from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from .factory import create_stt_engine


SUPPORTED_LANGUAGES = ["auto", "zh", "en", "yue", "ja", "ko"]


def find_project_root(explicit_root: str | None = None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "requirements.txt").exists() and (parent / "sylphos").exists():
            return parent
    return Path.cwd().resolve()


def check_imports() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for module_name in ("funasr", "torch", "modelscope"):
        try:
            __import__(module_name)
        except Exception:
            errors.append(
                f"依赖缺失: {module_name}。请运行: pip install -r requirements-asr.txt"
            )
    return (not errors), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sylphos SenseVoice ASR healthcheck")
    parser.add_argument("--audio", type=str, default=None, help="音频文件路径")
    parser.add_argument("--latest", action="store_true", help="使用 recordings/latest_command.wav")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--language", choices=SUPPORTED_LANGUAGES, default="auto")
    parser.add_argument("--model", type=str, default="iic/SenseVoiceSmall")
    parser.add_argument("--vad-model", type=str, default=None)
    parser.add_argument("--use-itn", dest="use_itn", action="store_true")
    parser.add_argument("--no-itn", dest="use_itn", action="store_false")
    parser.set_defaults(use_itn=True)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--warmup", type=str, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--project-root", type=str, default=None)
    parser.add_argument("--debug", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    started = time.perf_counter()

    project_root = find_project_root(args.project_root)
    latest_path = project_root / "recordings" / "latest_command.wav"

    payload: dict[str, Any] = {
        "ok": True,
        "python": sys.version,
        "cwd": str(Path.cwd().resolve()),
        "project_root": str(project_root),
        "model": args.model,
        "device": args.device,
        "audio_path": None,
        "warmup_audio_path": None,
        "warmup_seconds": 0.0,
        "text": None,
        "raw_text": None,
        "language": args.language,
        "elapsed_seconds": 0.0,
        "inference_seconds": 0.0,
        "dependencies_ok": False,
        "dependency_errors": [],
        "next_step": "",
        "errors": [],
    }

    deps_ok, dep_errors = check_imports()
    payload["dependencies_ok"] = deps_ok
    payload["dependency_errors"] = dep_errors
    if not deps_ok:
        payload["ok"] = False
        payload["errors"].extend(dep_errors)
        payload["next_step"] = "先安装依赖后重试: pip install -r requirements-asr.txt"
        payload["elapsed_seconds"] = time.perf_counter() - started
        return emit(payload, args.json)

    # 是否由用户“显式”要求识别某个音频。
    # - args.audio: 指定了具体路径
    # - args.latest: 指定了 latest 文件
    # 这个标志用于区分 warmup-only 场景，避免被自动 latest 选择干扰。
    explicit_audio_requested = bool(args.audio or args.latest)
    warmup_only = bool(args.warmup and not explicit_audio_requested)

    audio_path: Path | None = None
    selected_by_default = False
    if args.audio:
        audio_path = Path(args.audio).expanduser().resolve()
    elif args.latest:
        audio_path = latest_path
    # 仅在“非 warmup-only”时才自动回退到 latest，
    # 确保 `--warmup PATH` 不会触发额外识别。
    elif (not warmup_only) and latest_path.exists():
        audio_path = latest_path
        selected_by_default = True

    engine = None
    try:
        engine = create_stt_engine(
            provider="sensevoice",
            model=args.model,
            device=args.device,
            language=args.language,
            use_itn=args.use_itn,
            vad_model=args.vad_model,
            disable_update=True,
        )

        if args.download_only:
            payload["next_step"] = "模型已加载，可视为下载完成。"
            payload["elapsed_seconds"] = time.perf_counter() - started
            return emit(payload, args.json)

        if args.warmup:
            warmup_path = Path(args.warmup).expanduser().resolve()
            payload["warmup_audio_path"] = str(warmup_path)
            warmup_start = time.perf_counter()
            _ = engine.transcribe_file(warmup_path)
            payload["warmup_seconds"] = time.perf_counter() - warmup_start

            # warmup-only: 用户只希望做模型预热，不希望进入识别阶段。
            if warmup_only:
                payload["next_step"] = "预热完成。若需识别，请加 --audio 或 --latest。"
                payload["elapsed_seconds"] = time.perf_counter() - started
                return emit(payload, args.json)

        if audio_path is not None:
            payload["audio_path"] = str(audio_path)
            infer_start = time.perf_counter()
            result = engine.transcribe_file(audio_path)
            payload["inference_seconds"] = time.perf_counter() - infer_start
            payload["text"] = result.text
            payload["raw_text"] = result.raw_text
            payload["language"] = result.language
        else:
            payload["audio_path"] = None
    except Exception as exc:
        payload["ok"] = False
        payload["errors"].append(str(exc))
        if args.debug:
            payload["errors"].append(repr(exc))
    finally:
        if engine is not None:
            engine.close()

    payload["elapsed_seconds"] = time.perf_counter() - started
    if selected_by_default:
        payload["next_step"] = f"未指定音频，自动使用默认 latest 文件: {latest_path}"
    elif audio_path is None and not payload["next_step"]:
        payload["next_step"] = "未提供音频。下一步可运行: python -m sylphos.voice.stt.healthcheck --latest --device cpu"

    emit(payload, args.json)


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"OK: {payload['ok']}")
    print(f"Python: {payload['python']}")
    print(f"CWD: {payload['cwd']}")
    print(f"Project root: {payload['project_root']}")
    print(f"Model: {payload['model']}")
    print(f"Device: {payload['device']}")
    print("Dependencies: PASS" if payload["dependencies_ok"] else "Dependencies: FAIL")
    if payload["dependency_errors"]:
        print("Dependency errors:")
        for err in payload["dependency_errors"]:
            print(f"- {err}")
    print(f"Warmup audio path: {payload['warmup_audio_path']}")
    print(f"Warmup seconds: {payload['warmup_seconds']:.3f}")
    print(f"Audio path: {payload['audio_path']}")
    print(f"Text: {payload['text']}")
    print(f"Raw text: {payload['raw_text']}")
    print(f"Language: {payload['language']}")
    print(f"Inference seconds: {payload['inference_seconds']:.3f}")
    print(f"Elapsed seconds: {payload['elapsed_seconds']:.3f}")
    if payload["errors"]:
        print("Errors:")
        for err in payload["errors"]:
            print(f"- {err}")
    if payload["next_step"]:
        print(f"Next: {payload['next_step']}")


if __name__ == "__main__":
    main()
