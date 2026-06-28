"""Sylphos local configuration example.

Copy this file to ``local_config.py`` at the project root, then edit it for your
own machine. ``local_config.py`` is ignored by Git and must not contain values
that should be shared publicly.
"""

# ---------------------------------------------------------------------------
# Voice audio input
# ---------------------------------------------------------------------------
# Use None to let the operating system choose the default input device.
AUDIO_INPUT_DEVICE_INDEX = None
AUDIO_INPUT_DEVICE_NAME = None
INPUT_RATE = 44100
CHANNELS = 1
BLOCKSIZE = 4410
DTYPE = "float32"

# ---------------------------------------------------------------------------
# Wake word
# ---------------------------------------------------------------------------
# openwakeword_resource: load a model bundled with openwakeword by name.
# project_relative: load WAKEWORD_MODEL_RELATIVE_PATH relative to this repo.
WAKEWORD_MODEL_SOURCE = "openwakeword_resource"
WAKEWORD_MODEL_NAME = None
WAKEWORD_MODEL_RELATIVE_PATH = "models/wakeword/example.onnx"
WAKEWORD_THRESHOLD = 0.5
WAKEWORD_COOLDOWN_SECONDS = 2.0

# ---------------------------------------------------------------------------
# Command recording and VAD
# ---------------------------------------------------------------------------
RECORD_SAVE_MODE = "latest"  # off / latest / archive
RECORDINGS_DIR = "recordings"
LATEST_RECORD_FILENAME = "latest_command.wav"
COMMAND_RECORD_SECONDS = 0  # >0 fixed duration; <=0 uses VAD auto-stop.
VAD_ENABLED = True
VAD_THRESHOLD = 0.5
VAD_MIN_SPEECH_DURATION_MS = 150
VAD_MIN_SILENCE_DURATION_MS = 300
VAD_SPEECH_PAD_MS = 100
VAD_END_SILENCE_MS = 1000
VAD_PREBUFFER_MS = 400
VAD_CHECK_INTERVAL_MS = 200
VAD_SAMPLE_RATE = 16000

# ---------------------------------------------------------------------------
# Runtime defaults
# ---------------------------------------------------------------------------
RUNTIME_MODE = "event_driven"
WAKEWORD_PROVIDER = "openwakeword"
STT_PROVIDER = "dummy"
TTS_PROVIDER = "dummy"
TTS_MODEL_VERSION = "base"
TTS_VOICE_ID = "official"
TTS_TIMEOUT_SECONDS = 240
TTS_AUTO_PLAY = True
TTS_MAX_SPEAK_CHARS = None
TOOL_EXECUTOR_PROVIDER = "dummy"
AUDIO_ENABLED = False
AUDIO_DEVICE = None
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_BLOCKSIZE = 4410
RECORD_SECONDS = 0.0
CONSOLE_WAKE_SCORE_DISPLAY = "status"
WAKEWORD_SCORE_LOG_INTERVAL_SECONDS = 1.0
ASR_POST_PROCESSORS = ["normalize_text", "hotword_correction", "command_alias"]
HOTWORD_CORRECTIONS = {"example phrase": "Example"}
COMMAND_ALIASES = {"please open browser": "open browser"}
TTS_ON_WAKE = "Sylphos is listening"
TTS_ON_EXECUTING = "Processing"
TTS_ON_FAILED = "Execution failed; check the text result"
DUMMY_STT_TEXT = "open browser"

# ---------------------------------------------------------------------------
# OpenClaw / executor integration
# ---------------------------------------------------------------------------
OPENCLAW_MODE = "cli"
OPENCLAW_CLI = "openclaw"
OPENCLAW_CLI_PATH = "openclaw"
OPENCLAW_WORKDIR = None
OPENCLAW_WORKSPACE = None
OPENCLAW_TIMEOUT_SECONDS = 60
OPENCLAW_DRY_RUN = True
OPENCLAW_WS_URL = "ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_WS_URL = "ws://127.0.0.1:18789"
OPENCLAW_API_URL = "http://127.0.0.1:18789"
OPENCLAW_HTTP_BASE_URL = "http://127.0.0.1:18789"
OPENCLAW_TOKEN = None
OPENCLAW_AUTH_TOKEN = None
OPENCLAW_CLI_AGENT_ID = None
OPENCLAW_CLI_MODEL = None
OPENCLAW_CLI_SESSION_KEY = "sylphos-local"
OPENCLAW_CLI_LOCAL = False
OPENCLAW_CLI_DELIVER = False
OPENCLAW_CLI_JSON = False

# ---------------------------------------------------------------------------
# TTS / ASR service endpoints and model references
# ---------------------------------------------------------------------------
COSYVOICE_URL = "http://127.0.0.1:8000"
COSYVOICE_MODEL_PATH = None
COSYVOICE_RL_MODEL_PATH = None
COSYVOICE_PROMPT_DIR = None
SENSEVOICE_MODEL = "iic/SenseVoiceSmall"
SENSEVOICE_VAD_MODEL = None
