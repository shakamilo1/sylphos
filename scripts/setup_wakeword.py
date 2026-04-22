from __future__ import annotations

"""WakeWord 配置向导。

基于当前仓库真实配置机制：
- 默认配置：config/voice.py
- 本地覆盖：config/local_config.py
"""

import importlib.resources as ir
from pathlib import Path

import sounddevice as sd

from config import voice as voice_config

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_PATH = BASE_DIR / "config" / "local_config.py"


def get_openwakeword_model_dir() -> Path:
    return Path(str(ir.files("openwakeword") / "resources" / "models"))


def list_input_devices() -> list[tuple[int, dict]]:
    devices = sd.query_devices()
    result: list[tuple[int, dict]] = []

    print("\n可用输入设备：")
    print("-" * 90)
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            result.append((idx, dev))
            print(
                f"[{idx}] {dev['name']} | in={dev['max_input_channels']} | "
                f"default_sr={int(dev['default_samplerate'])}"
            )
    print("-" * 90)
    return result


def ask_with_default(prompt: str, default: str) -> str:
    raw = input(f"{prompt}（默认 {default}）: ").strip()
    return raw if raw else default


def ask_int(prompt: str, default: int, *, min_value: int | None = None) -> int:
    while True:
        raw = ask_with_default(prompt, str(default))
        try:
            value = int(raw)
            if min_value is not None and value < min_value:
                print(f"输入必须 >= {min_value}，请重试。")
                continue
            return value
        except ValueError:
            print("请输入整数。")


def ask_float(prompt: str, default: float, *, min_value: float | None = None) -> float:
    while True:
        raw = ask_with_default(prompt, str(default))
        try:
            value = float(raw)
            if min_value is not None and value < min_value:
                print(f"输入必须 >= {min_value}，请重试。")
                continue
            return value
        except ValueError:
            print("请输入数字。")


def ask_bool(prompt: str, default: bool) -> bool:
    default_text = "y" if default else "n"
    while True:
        raw = ask_with_default(f"{prompt} [y/n]", default_text).lower()
        if raw in {"y", "yes", "1"}:
            return True
        if raw in {"n", "no", "0"}:
            return False
        print("请输入 y 或 n。")


def choose_input_device() -> tuple[int | None, str | None, int]:
    devices = list_input_devices()

    if not devices:
        print("未发现可用输入设备，将使用系统默认设备。")
        return None, None, int(voice_config.INPUT_RATE)

    while True:
        raw = input("请选择输入设备编号（直接回车=系统默认）: ").strip()
        if not raw:
            print("已选择：系统默认输入设备")
            return None, None, int(voice_config.INPUT_RATE)

        try:
            idx = int(raw)
        except ValueError:
            print("编号必须是整数，请重试。")
            continue

        try:
            dev = sd.query_devices(idx)
        except Exception as exc:
            print(f"设备编号无效：{exc}")
            continue

        if dev["max_input_channels"] <= 0:
            print("该设备不是输入设备，请重试。")
            continue

        name = str(dev["name"])
        sr = int(dev["default_samplerate"])
        print(f"已选择设备：[{idx}] {name}")
        return idx, name, sr


def choose_model() -> tuple[str, str | None, str | None]:
    while True:
        print("\nwakeword 模型来源：")
        print("[1] openwakeword_resource（openwakeword 包内模型）")
        print("[2] project_relative（项目相对路径）")
        mode = ask_with_default("请选择模型来源编号", "1")

        if mode == "1":
            default_dir = get_openwakeword_model_dir()
            models = sorted(default_dir.glob("*.onnx"))
            print(f"\nopenwakeword 模型目录：{default_dir}")
            if not models:
                print("未找到任何 .onnx 模型，请先执行模型下载。")
                continue

            for i, p in enumerate(models, start=1):
                print(f"[{i}] {p.name}")

            while True:
                pick = ask_with_default("请选择模型编号", "1")
                try:
                    selected = models[int(pick) - 1]
                    return "openwakeword_resource", None, selected.name
                except Exception:
                    print("模型编号无效，请重试。")

        if mode == "2":
            rel = ask_with_default("请输入模型相对路径（例如 models/wakeword/your_model.onnx）", "models/wakeword/hey_jarvis_v0.1.onnx")
            model_path = Path(rel)
            if not model_path.is_absolute():
                model_path = BASE_DIR / model_path
            if not model_path.exists():
                print(f"模型文件不存在：{model_path}")
                continue
            return "project_relative", rel, None

        print("来源编号无效，请输入 1 或 2。")


def choose_record_mode() -> str:
    print("\n录音保存模式：")
    print("[1] latest（仅保留最新一条）")
    print("[2] archive（每次保存独立文件）")
    print("[3] off（不保存文件，仅回调）")
    mapping = {"1": "latest", "2": "archive", "3": "off"}

    while True:
        raw = ask_with_default("请选择保存模式编号", "1")
        if raw in mapping:
            return mapping[raw]
        print("输入无效，请输入 1/2/3。")


def write_local_config(config_data: dict[str, object]) -> None:
    content = f'''AUDIO_INPUT_DEVICE_INDEX = {repr(config_data['device_index'])}
AUDIO_INPUT_DEVICE_NAME = {repr(config_data['device_name'])}

INPUT_RATE = {config_data['input_rate']}
CHANNELS = {config_data['channels']}
BLOCKSIZE = {config_data['blocksize']}
DTYPE = {repr(config_data['dtype'])}

WAKEWORD_MODEL_SOURCE = {repr(config_data['model_source'])}
WAKEWORD_MODEL_NAME = {repr(config_data['model_name'])}
WAKEWORD_MODEL_RELATIVE_PATH = {repr(config_data['model_relative_path'])}
WAKEWORD_THRESHOLD = {config_data['threshold']}
WAKEWORD_COOLDOWN_SECONDS = {config_data['cooldown']}

RECORD_SAVE_MODE = {repr(config_data['record_save_mode'])}
RECORDINGS_DIR = {repr(config_data['recordings_dir'])}
LATEST_RECORD_FILENAME = {repr(config_data['latest_filename'])}

COMMAND_RECORD_SECONDS = {config_data['record_seconds']}
VAD_ENABLED = {config_data['vad_enabled']}
VAD_THRESHOLD = {config_data['vad_threshold']}
VAD_MIN_SPEECH_DURATION_MS = {config_data['vad_min_speech_duration_ms']}
VAD_MIN_SILENCE_DURATION_MS = {config_data['vad_min_silence_duration_ms']}
VAD_SPEECH_PAD_MS = {config_data['vad_speech_pad_ms']}
VAD_END_SILENCE_MS = {config_data['vad_end_silence_ms']}
VAD_PREBUFFER_MS = {config_data['vad_prebuffer_ms']}
VAD_CHECK_INTERVAL_MS = {config_data['vad_check_interval_ms']}
VAD_SAMPLE_RATE = {config_data['vad_sample_rate']}
'''

    LOCAL_CONFIG_PATH.write_text(content, encoding="utf-8")
    print(f"\n已生成配置文件：{LOCAL_CONFIG_PATH}")


def main() -> None:
    print("=== Sylphos 配置向导（wakeword + 录音）===")

    device_index, device_name, detected_sr = choose_input_device()
    model_source, model_relative_path, model_name = choose_model()

    input_rate = ask_int("输入采样率", detected_sr if detected_sr > 0 else int(voice_config.INPUT_RATE), min_value=8000)
    channels = ask_int("声道数", int(voice_config.CHANNELS), min_value=1)
    blocksize = ask_int("blocksize", int(voice_config.BLOCKSIZE), min_value=1)
    dtype = ask_with_default("dtype", str(voice_config.DTYPE))

    threshold = ask_float("唤醒阈值", float(voice_config.WAKEWORD_THRESHOLD), min_value=0.0)
    cooldown = ask_float("唤醒冷却秒数", float(voice_config.WAKEWORD_COOLDOWN_SECONDS), min_value=0.0)

    recordings_dir = ask_with_default("录音保存目录", str(voice_config.RECORDINGS_DIR))
    record_save_mode = choose_record_mode()
    latest_filename = ask_with_default("latest 模式文件名", str(voice_config.LATEST_RECORD_FILENAME))

    record_seconds = ask_float(
        "固定录音秒数（<=0 表示改用 VAD 自动结束）",
        float(voice_config.COMMAND_RECORD_SECONDS),
    )
    vad_enabled = ask_bool("启用 VAD", bool(voice_config.VAD_ENABLED))

    vad_threshold = ask_float("VAD 阈值", float(voice_config.VAD_THRESHOLD), min_value=0.0)
    vad_min_speech_duration_ms = ask_int(
        "VAD 最短语音时长(ms)",
        int(voice_config.VAD_MIN_SPEECH_DURATION_MS),
        min_value=1,
    )
    vad_min_silence_duration_ms = ask_int(
        "VAD 最短静音时长(ms)",
        int(voice_config.VAD_MIN_SILENCE_DURATION_MS),
        min_value=1,
    )
    vad_speech_pad_ms = ask_int("VAD speech_pad(ms)", int(voice_config.VAD_SPEECH_PAD_MS), min_value=0)
    vad_end_silence_ms = ask_int("VAD 结束静音阈值(ms)", int(voice_config.VAD_END_SILENCE_MS), min_value=1)
    vad_prebuffer_ms = ask_int("VAD 预缓冲(ms)", int(voice_config.VAD_PREBUFFER_MS), min_value=0)
    vad_check_interval_ms = ask_int("VAD 检测间隔(ms)", int(voice_config.VAD_CHECK_INTERVAL_MS), min_value=1)
    vad_sample_rate = ask_int("VAD 采样率", int(voice_config.VAD_SAMPLE_RATE), min_value=8000)

    write_local_config(
        {
            "device_index": device_index,
            "device_name": device_name,
            "input_rate": input_rate,
            "channels": channels,
            "blocksize": blocksize,
            "dtype": dtype,
            "model_source": model_source,
            "model_relative_path": model_relative_path,
            "model_name": model_name,
            "threshold": threshold,
            "cooldown": cooldown,
            "recordings_dir": recordings_dir,
            "record_save_mode": record_save_mode,
            "latest_filename": latest_filename,
            "record_seconds": record_seconds,
            "vad_enabled": vad_enabled,
            "vad_threshold": vad_threshold,
            "vad_min_speech_duration_ms": vad_min_speech_duration_ms,
            "vad_min_silence_duration_ms": vad_min_silence_duration_ms,
            "vad_speech_pad_ms": vad_speech_pad_ms,
            "vad_end_silence_ms": vad_end_silence_ms,
            "vad_prebuffer_ms": vad_prebuffer_ms,
            "vad_check_interval_ms": vad_check_interval_ms,
            "vad_sample_rate": vad_sample_rate,
        }
    )

    print("\n配置完成。建议下一步运行：python -m scripts.test_wakeword_pipeline show-config")


if __name__ == "__main__":
    main()
