from __future__ import annotations

"""统一测试入口。

覆盖：设备检查、模型检查、配置检查、录音测试、唤醒测试、全链路测试。
"""

import argparse
import importlib.resources as ir
import logging
import time
from pathlib import Path

from config import voice as voice_config
from scripts.runtime_bootstrap import resolve_wakeword_model_path


def _require_sounddevice():
    """按需导入 sounddevice，避免 --help 依赖音频库。"""
    try:
        import sounddevice as sd

        return sd
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "当前命令需要 sounddevice。请先在虚拟环境安装依赖后重试。"
        ) from exc


def _create_runtime_stack() -> dict[str, object]:
    """按需导入运行装配，避免纯检查命令触发音频依赖。"""
    from scripts.runtime_bootstrap import create_runtime_stack

    return create_runtime_stack()


def list_devices() -> None:
    sd = _require_sounddevice()

    print("=== 输入设备列表 ===")
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            print(
                f"[{idx}] {dev['name']} | in={dev['max_input_channels']} | "
                f"default_sr={int(dev['default_samplerate'])}"
            )


def list_models() -> None:
    print("=== openwakeword 可用模型 ===")
    try:
        model_dir = Path(str(ir.files("openwakeword") / "resources" / "models"))
        models = sorted(model_dir.glob("*.onnx"))
    except Exception as exc:  # noqa: BLE001
        print(f"无法读取 openwakeword 内置模型目录：{exc}")
        models = []
        model_dir = None

    if not models:
        print("未找到模型。可运行 python download.py 下载。")
    else:
        print(f"模型目录: {model_dir}")
        for p in models:
            print(f"- {p.name}")

    if voice_config.WAKEWORD_MODEL_SOURCE == "project_relative":
        resolved = resolve_wakeword_model_path()
        print(f"当前配置 project_relative 路径: {resolved}")


def show_config() -> None:
    print("=== 当前生效配置（config.voice）===")
    keys = [
        "AUDIO_INPUT_DEVICE_INDEX",
        "AUDIO_INPUT_DEVICE_NAME",
        "INPUT_RATE",
        "CHANNELS",
        "BLOCKSIZE",
        "DTYPE",
        "WAKEWORD_MODEL_SOURCE",
        "WAKEWORD_MODEL_NAME",
        "WAKEWORD_MODEL_RELATIVE_PATH",
        "WAKEWORD_THRESHOLD",
        "WAKEWORD_COOLDOWN_SECONDS",
        "RECORD_SAVE_MODE",
        "RECORDINGS_DIR",
        "LATEST_RECORD_FILENAME",
        "COMMAND_RECORD_SECONDS",
        "VAD_ENABLED",
        "VAD_THRESHOLD",
        "VAD_MIN_SPEECH_DURATION_MS",
        "VAD_MIN_SILENCE_DURATION_MS",
        "VAD_SPEECH_PAD_MS",
        "VAD_END_SILENCE_MS",
        "VAD_PREBUFFER_MS",
        "VAD_CHECK_INTERVAL_MS",
        "VAD_SAMPLE_RATE",
    ]
    for key in keys:
        print(f"{key} = {getattr(voice_config, key)}")


def check_config() -> int:
    print("=== 配置自检 ===")
    ok = True

    if voice_config.INPUT_RATE <= 0:
        print("[FAIL] INPUT_RATE 必须 > 0")
        ok = False

    if voice_config.CHANNELS <= 0:
        print("[FAIL] CHANNELS 必须 > 0")
        ok = False

    if voice_config.BLOCKSIZE <= 0:
        print("[FAIL] BLOCKSIZE 必须 > 0")
        ok = False

    try:
        model_path = resolve_wakeword_model_path()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] 模型路径解析失败: {exc}")
        ok = False
        model_path = None

    if model_path is not None and not model_path.exists():
        print(f"[FAIL] 模型文件不存在: {model_path}")
        ok = False
    else:
        print(f"[OK] 模型路径: {model_path if model_path else 'openwakeword 默认内置模型集'}")

    if voice_config.RECORD_SAVE_MODE not in {"off", "latest", "archive"}:
        print("[FAIL] RECORD_SAVE_MODE 必须是 off/latest/archive")
        ok = False

    if voice_config.COMMAND_RECORD_SECONDS <= 0 and not voice_config.VAD_ENABLED:
        print("[FAIL] COMMAND_RECORD_SECONDS <= 0 时必须启用 VAD")
        ok = False

    if ok:
        print("[OK] 配置自检通过")
        return 0

    print("[FAIL] 配置存在问题，请先修正")
    return 1


def test_record(mode: str, duration: float) -> int:
    print(f"=== 录音测试（{mode}）===")
    stack = _create_runtime_stack()
    recorder = stack["recorder"]
    hub = stack["hub"]

    if mode == "timed":
        print(f"开始定时录音 {duration:.1f}s，请说话...")
        recorder.start_recording(duration_seconds=duration)
        wait_seconds = duration + 1.0
    else:
        if not voice_config.VAD_ENABLED:
            print("VAD 未启用，无法执行 VAD 测试")
            return 1
        print("开始 VAD 录音，请说话并停顿以自动结束...")
        recorder.start_recording(duration_seconds=0)
        wait_seconds = duration

    hub.start()
    try:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if not recorder.is_recording():
                print("录音已结束")
                return 0
            time.sleep(0.1)

        if recorder.is_recording():
            print("测试时间结束，录音仍在进行（请检查参数或环境噪声）")
            return 1
        return 0
    finally:
        hub.stop()
        recorder.close()
        stack["wake"].close()


def test_wakeword_listen(duration: float) -> int:
    print(f"=== 唤醒监听测试（{duration:.1f}s）===")
    stack = _create_runtime_stack()
    hub = stack["hub"]
    wake = stack["wake"]

    wake.set_callback(lambda name, score: print(f"[DETECTED] {name} score={score:.3f}"))

    hub.unsubscribe(stack["recorder"].consume)
    hub.start()
    try:
        print("正在监听唤醒词... Ctrl+C 可提前结束")
        time.sleep(duration)
        print("监听测试结束")
        return 0
    except KeyboardInterrupt:
        print("用户中断")
        return 0
    finally:
        hub.stop()
        stack["recorder"].close()
        wake.close()


def test_full_pipeline(duration: float) -> int:
    from scripts.runtime_bootstrap import start_runtime_stack, stop_runtime_stack

    print(f"=== 全链路测试（{duration:.1f}s）===")
    stack = _create_runtime_stack()
    start_runtime_stack(stack)
    try:
        print("全链路运行中：说唤醒词 -> 触发录音。")
        print("提示：当前策略下录音完成后不会自动恢复唤醒，可在终端输入 r + 回车恢复。")
        end = time.time() + duration
        while time.time() < end:
            time.sleep(0.2)
        print("全链路测试结束")
        return 0
    except KeyboardInterrupt:
        print("用户中断")
        return 0
    finally:
        stop_runtime_stack(stack)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sylphos 统一测试入口")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-devices", help="查看音频输入设备")
    sub.add_parser("list-models", help="查看 openwakeword 可用模型")
    sub.add_parser("show-config", help="打印当前配置")
    sub.add_parser("check-config", help="配置自检")

    timed = sub.add_parser("test-timed-record", help="测试定时录音")
    timed.add_argument("--duration", type=float, default=3.0)

    vad = sub.add_parser("test-vad-record", help="测试 VAD 录音")
    vad.add_argument("--duration", type=float, default=12.0, help="最大等待秒数")

    wake = sub.add_parser("test-wakeword-listen", help="测试唤醒监听")
    wake.add_argument("--duration", type=float, default=15.0)

    full = sub.add_parser("test-full-pipeline", help="测试完整链路")
    full.add_argument("--duration", type=float, default=20.0)

    return parser


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "list-devices":
            list_devices()
            return 0
        if args.command == "list-models":
            list_models()
            return 0
        if args.command == "show-config":
            show_config()
            return 0
        if args.command == "check-config":
            return check_config()
        if args.command == "test-timed-record":
            return test_record("timed", args.duration)
        if args.command == "test-vad-record":
            return test_record("vad", args.duration)
        if args.command == "test-wakeword-listen":
            return test_wakeword_listen(args.duration)
        if args.command == "test-full-pipeline":
            return test_full_pipeline(args.duration)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
