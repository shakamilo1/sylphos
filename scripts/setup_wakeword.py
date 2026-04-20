from __future__ import annotations

"""WakeWord 配置向导。

脚本层职责：
1) 引导用户选择输入设备与 wakeword 模型；
2) 采集阈值/冷却/录音参数；
3) 将覆盖配置写入 `config/local_config.py`。

推荐从项目根目录运行：`python -m scripts.setup_wakeword`。
"""

import importlib.resources as ir
from pathlib import Path

import sounddevice as sd


BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_CONFIG_PATH = BASE_DIR / "config" / "local_config.py"


def get_openwakeword_model_dir() -> Path:
    """返回 openwakeword 包内默认模型目录。"""
    return Path(str(ir.files("openwakeword") / "resources" / "models"))


def list_input_devices() -> list[tuple[int, dict]]:
    """列出系统可用输入设备并返回候选列表。"""
    devices = sd.query_devices()
    result: list[tuple[int, dict]] = []

    print("\n可用输入设备：")
    print("-" * 80)
    for idx, dev in enumerate(devices):
        if dev["max_input_channels"] > 0:
            result.append((idx, dev))
            print(
                f"[{idx}] {dev['name']} | "
                f"in={dev['max_input_channels']} | "
                f"default_sr={dev['default_samplerate']}"
            )
    print("-" * 80)
    return result


def choose_input_device() -> tuple[int | None, str | None, int]:
    """设备选择流程：用户可选具体设备，也可回车使用系统默认。"""
    devices = list_input_devices()

    if not devices:
        print("未发现可用输入设备，将使用系统默认设备。")
        return None, None, 44100

    raw = input("请选择输入设备编号（直接回车=系统默认）: ").strip()
    if not raw:
        print("已选择：系统默认输入设备")
        return None, None, 44100

    idx = int(raw)
    dev = sd.query_devices(idx)
    name = str(dev["name"])
    sr = int(dev["default_samplerate"])
    print(f"已选择设备：[{idx}] {name}")
    return idx, name, sr


def list_models(model_dir: Path) -> list[Path]:
    """列出指定目录中的 .onnx 模型。"""
    models = sorted(model_dir.glob("*.onnx"))

    print("\n可用 wakeword 模型：")
    print("-" * 80)
    for i, p in enumerate(models, start=1):
        print(f"[{i}] {p.name}")
    print("-" * 80)

    return models


def choose_model() -> tuple[str, str | None, str]:
    """模型选择流程，当前默认走 openwakeword_resource。"""
    default_dir = get_openwakeword_model_dir()

    print("\n默认模型来源：openwakeword_resource")
    print(f"模型目录：{default_dir}")

    models = list_models(default_dir)
    if not models:
        raise FileNotFoundError(f"目录中未找到 .onnx 模型：{default_dir}")

    raw = input("请选择模型编号: ").strip()
    if not raw:
        raise ValueError("必须选择一个模型编号。")

    selected = models[int(raw) - 1]
    print(f"已选择模型：{selected.name}")

    # source, relative_path, model_name
    return "openwakeword_resource", None, selected.name


def ask_with_default(prompt: str, default: str) -> str:
    """读取用户输入，空输入时采用默认值。"""
    raw = input(f"{prompt}（默认 {default}）: ").strip()
    return raw if raw else default


def write_local_config(
    *,
    device_index: int | None,
    device_name: str | None,
    input_rate: int,
    model_source: str,
    model_relative_path: str | None,
    model_name: str,
    threshold: float,
    cooldown: float,
    recordings_dir: str,
    record_seconds: float,
) -> None:
    """将向导结果写入 config/local_config.py。"""
    content = f'''AUDIO_INPUT_DEVICE_INDEX = {repr(device_index)}
AUDIO_INPUT_DEVICE_NAME = {repr(device_name)}

INPUT_RATE = {input_rate}
CHANNELS = 1
BLOCKSIZE = 4410
DTYPE = "float32"

WAKEWORD_MODEL_SOURCE = {repr(model_source)}
WAKEWORD_MODEL_NAME = {repr(model_name)}
WAKEWORD_MODEL_RELATIVE_PATH = {repr(model_relative_path)}
WAKEWORD_THRESHOLD = {threshold}
WAKEWORD_COOLDOWN_SECONDS = {cooldown}

RECORDINGS_DIR = {repr(recordings_dir)}
COMMAND_RECORD_SECONDS = {record_seconds}
'''

    LOCAL_CONFIG_PATH.write_text(content, encoding="utf-8")
    print(f"\n已生成配置文件：{LOCAL_CONFIG_PATH}")


def main() -> None:
    """配置入口：按“设备 -> 模型 -> 参数 -> 写入配置”顺序执行。"""
    print("=== Sylphos wakeword 配置向导 ===")

    device_index, device_name, detected_sr = choose_input_device()
    model_source, model_relative_path, model_name = choose_model()

    input_rate = int(
        ask_with_default("输入采样率", str(detected_sr if detected_sr > 0 else 44100))
    )
    threshold = float(ask_with_default("唤醒阈值", "0.5"))
    cooldown = float(ask_with_default("唤醒冷却秒数", "2.0"))
    recordings_dir = ask_with_default("录音保存目录", "recordings")
    record_seconds = float(ask_with_default("固定录音秒数", "5.0"))

    write_local_config(
        device_index=device_index,
        device_name=device_name,
        input_rate=input_rate,
        model_source=model_source,
        model_relative_path=model_relative_path,
        model_name=model_name,
        threshold=threshold,
        cooldown=cooldown,
        recordings_dir=recordings_dir,
        record_seconds=record_seconds,
    )


if __name__ == "__main__":
    main()
