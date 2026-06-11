RUNTIME_MODE = "event_driven"

WAKEWORD_PROVIDER = "openwakeword"
STT_PROVIDER = "dummy"
TTS_PROVIDER = "dummy"
TOOL_EXECUTOR_PROVIDER = "dummy"

AUDIO_ENABLED = False
AUDIO_DEVICE = None
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_BLOCKSIZE = 4410
RECORD_SECONDS = 0.0

ASR_POST_PROCESSORS = [
    "normalize_text",
    "hotword_correction",
    "command_alias",
]

HOTWORD_CORRECTIONS = {
    "欧喷克劳": "OpenClaw",
    "欧盆克劳": "OpenClaw",
    "浏览气": "浏览器",
}

COMMAND_ALIASES = {
    "帮我打开浏览器": "打开浏览器",
    "请打开浏览器": "打开浏览器",
    "打开一下浏览器": "打开浏览器",
    "帮我打开记事本": "打开记事本",
    "请打开记事本": "打开记事本",
}

TTS_ON_WAKE = "Sylphos在聆听着"
TTS_ON_EXECUTING = "正在处理"
TTS_ON_FAILED = "执行失败，请查看文本结果"

OPENCLAW_CLI = "openclaw"
OPENCLAW_TIMEOUT_SECONDS = 60
OPENCLAW_DRY_RUN = True
COSYVOICE_URL = "http://127.0.0.1:8000"
DUMMY_STT_TEXT = "打开浏览器"
