from __future__ import annotations

"""语音链路配置。

该模块提供 wakeword + 录音相关默认参数，并在可用时加载
`config/local_config.py` 覆盖默认值（由 setup_wakeword 脚本生成）。
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


try:
    from config.local_config import *  # noqa: F403,F401
except ImportError:
    pass
