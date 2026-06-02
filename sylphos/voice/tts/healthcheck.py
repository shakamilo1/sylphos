from __future__ import annotations

"""CosyVoice TTS healthcheck entrypoint.

Run with:
    python -m sylphos.voice.tts.healthcheck
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from sylphos.runtime.events import EventBus, RuntimeEvent, TTSRequested
from sylphos.runtime.tts_handler import TTSHandler

from .factory import create_tts_engine

MIN_PYTHON = (3, 12)
DEFAULT_MODEL = "iic/CosyVoice3-0.5B"
DEFAULT_TEXT = "你好，我是 Sylphos。"
DEFAULT_OUTPUT = Path("outputs/tts/latest_tts.wav")


def find_project_root(explicit_root: str | None = None) -> Path:
    if explicit_root:
        return Path(explicit_root).expanduser().resolve()

    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "requirements.txt").exists() and (parent / "sylphos").exists():
            return parent
    return Path.cwd().resolve()


def check_python_version() -> tuple[bool, str | None]:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(map(str, MIN_PYTHON))
        return False, f"Sylphos TTS requires Python >= {required}; current is {sys.version.split()[0]}"
    return True, None


def check_imports() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for module_name in ("torch", "torchaudio", "modelscope", "cosyvoice"):
        try:
            __import__(module_name)
        except Exception:
            if module_name == "cosyvoice":
                errors.append(
                    "依赖缺失: cosyvoice。requirements-tts.txt 不包含 CosyVoice 本体，"
                    "请按 docs/tts_cosyvoice.md 从 CosyVoice 官方仓库源码安装。"
                )
            else:
                errors.append(f"依赖缺失: {module_name}。请运行: pip install -r requirements-tts.txt")
    return (not errors), errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sylphos CosyVoice TTS healthcheck")
    parser.add_argument("--text", type=str, default=None, help="要合成的文本")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="输出 wav 路径")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="CosyVoice 模型名或本地模型目录")
    parser.add_argument("--device", type=str, default="cpu", help="推理设备，例如 cpu 或 cuda:0")
    parser.add_argument("--download-only", action="store_true", help="只加载模型，用于下载/初始化")
    parser.add_argument("--warmup", action="store_true", help="使用默认短句预热模型")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--project-root", type=str, default=None, help="可选项目根目录")
    parser.add_argument("--debug", action="store_true", help="输出详细异常")
    parser.add_argument("--runtime", action="store_true", help="模拟 Runtime EventBus 流程")
    parser.add_argument("--speaker", type=str, default=None, help="可选 speaker / voice 名称")
    parser.add_argument("--prompt-wav", type=str, default=None, help="可选 zero-shot prompt wav")
    parser.add_argument("--prompt-text", type=str, default="", help="可选 zero-shot prompt 文本")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    started = time.perf_counter()
    cwd = Path.cwd().resolve()
    project_root = find_project_root(args.project_root)
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = (project_root / output_path).resolve()

    py_ok, py_error = check_python_version()
    deps_ok, dep_errors = check_imports()
    errors: list[str] = []
    if py_error:
        errors.append(py_error)

    payload: dict[str, Any] = {
        "ok": py_ok and deps_ok,
        "python": sys.version.split()[0],
        "cwd": str(cwd),
        "project_root": str(project_root),
        "model": args.model,
        "device": args.device,
        "text": args.text,
        "output_path": str(output_path),
        "elapsed_seconds": 0.0,
        "dependencies_ok": deps_ok,
        "dependency_errors": dep_errors,
        "errors": errors,
        "event_published": False,
        "events": [],
        "sample_rate": None,
        "next_step": "",
    }

    engine = None
    try:
        if not py_ok:
            raise RuntimeError(py_error)

        engine = create_tts_engine(provider="cosyvoice", model=args.model, device=args.device)

        if args.download_only:
            payload["next_step"] = "模型已加载，可视为下载/初始化完成。"
            return emit(payload, args.json, started)

        synth_text = args.text
        if args.warmup and not synth_text:
            synth_text = DEFAULT_TEXT
            payload["text"] = synth_text

        if synth_text and args.runtime:
            if engine is not None:
                engine.close()
                engine = None
            event_bus = EventBus()

            def _collector(event: RuntimeEvent) -> None:
                payload["events"].append({"event_type": event.event_type, "payload": event.payload})

            event_bus.subscribe("tts.completed", _collector)
            handler = TTSHandler(event_bus=event_bus, tts_provider="cosyvoice", model=args.model, device=args.device)
            handler.start()
            # 关键节点：模拟上游 LLM/Orchestrator 发布 TTSRequested 事件。
            event_bus.publish(
                TTSRequested(
                    text=synth_text,
                    output_path=str(output_path),
                    voice=args.speaker,
                    speaker=args.speaker,
                    prompt_wav=args.prompt_wav,
                    prompt_text=args.prompt_text,
                )
            )
            handler.stop()
            payload["event_published"] = bool(payload["events"])
            if payload["events"]:
                tts_payload = payload["events"][-1]["payload"]
                payload["output_path"] = tts_payload.get("audio_path") or str(output_path)
                payload["sample_rate"] = tts_payload.get("sample_rate")
        elif synth_text:
            assert engine is not None
            result = engine.synthesize_to_file(
                synth_text,
                output_path,
                speaker=args.speaker,
                prompt_wav=args.prompt_wav,
                prompt_text=args.prompt_text,
            )
            payload["output_path"] = str(result.audio_path) if result.audio_path else str(output_path)
            payload["sample_rate"] = result.sample_rate
        else:
            payload["next_step"] = (
                "未提供文本。示例: python -m sylphos.voice.tts.healthcheck "
                "--text \"你好，我是 Sylphos。\" --output outputs/tts/latest_tts.wav --device cpu"
            )
    except Exception as exc:
        payload["ok"] = False
        payload["errors"].append(str(exc))
        if args.debug:
            payload["errors"].append(repr(exc))
    finally:
        if engine is not None:
            engine.close()

    emit(payload, args.json, started)


def emit(payload: dict[str, Any], as_json: bool, started: float) -> None:
    payload["elapsed_seconds"] = time.perf_counter() - started
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
    print(f"Text: {payload['text']}")
    print(f"Output path: {payload['output_path']}")
    print(f"Sample rate: {payload['sample_rate']}")
    print(f"Event published: {payload['event_published']}")
    print(f"Events: {payload['events']}")
    print(f"Elapsed seconds: {payload['elapsed_seconds']:.3f}")
    if payload["errors"]:
        print("Errors:")
        for err in payload["errors"]:
            print(f"- {err}")
    if payload["next_step"]:
        print(f"Next: {payload['next_step']}")


if __name__ == "__main__":
    main()
