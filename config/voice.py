from __future__ import annotations

"""语音链路配置。

该模块提供 wakeword + 录音相关默认参数，并在可用时加载
项目根目录 `local_config.py` 覆盖默认值（由 setup_config.py 生成）。
"""

# 音频输入
AUDIO_INPUT_DEVICE_INDEX = None
AUDIO_INPUT_DEVICE_NAME = None

INPUT_RATE = 44100
CHANNELS = 1
BLOCKSIZE = 4410
DTYPE = "float32"

# 唤醒词
WAKEWORD_MODEL_SOURCE = "openwakeword_resource"
WAKEWORD_MODEL_NAME = None
WAKEWORD_MODEL_RELATIVE_PATH = None
WAKEWORD_THRESHOLD = 0.5
WAKEWORD_COOLDOWN_SECONDS = 2.0

# 录音
RECORD_SAVE_MODE = "latest"  # off / latest / archive
RECORDINGS_DIR = "recordings"
LATEST_RECORD_FILENAME = "latest_command.wav"

# > 0: 固定时长录音
# <= 0: 使用 VAD 自动结束
COMMAND_RECORD_SECONDS = 0

# VAD（仅在 COMMAND_RECORD_SECONDS <= 0 时生效）
VAD_ENABLED = True
VAD_THRESHOLD = 0.5
VAD_MIN_SPEECH_DURATION_MS = 150
VAD_MIN_SILENCE_DURATION_MS = 300
VAD_SPEECH_PAD_MS = 100
VAD_END_SILENCE_MS = 1000
VAD_PREBUFFER_MS = 400
VAD_CHECK_INTERVAL_MS = 200
VAD_SAMPLE_RATE = 16000


def _load_local_config() -> None:
    """Load project-root local_config.py overrides without exposing personal data in git."""

    import importlib.util
    from pathlib import Path

    local_config = Path(__file__).resolve().parents[1] / "local_config.py"
    if not local_config.is_file():
        return
    spec = importlib.util.spec_from_file_location("sylphos_local_config", local_config)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载本地配置文件: {local_config}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(f"本地配置文件加载失败 {local_config}: {exc}") from exc
    globals().update({name: getattr(module, name) for name in dir(module) if name.isupper()})


_load_local_config()
