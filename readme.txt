Sylphos 当前版本使用说明（语音链路）
====================================

> 本文档只描述当前仓库已经实现并可直接使用的能力。项目最低 Python 版本为 **Python 3.12**。

一、项目简介
-----------
当前仓库已实现模块化语音运行时，核心能力包括：
1) 麦克风音频采集与分发（AudioHub）
2) OpenWakeWord 唤醒词检测
3) 录音（固定时长模式 + VAD 自动结束模式）
4) SenseVoice / FunASR STT（独立健康检查 + Runtime EventBus）
5) CosyVoice TTS（独立健康检查 + Runtime EventBus）
6) 统一配置向导与 wakeword/recorder 测试入口

二、语音链路相关目录与脚本
------------------------
- `config/voice.py`：默认配置
- `config/local_config.py`：本地覆盖配置（由向导生成）
- `scripts/setup_wakeword.py`：配置向导
- `scripts/test_wakeword_pipeline.py`：统一测试 CLI
- `scripts/run_wakeword_pipeline.py`：正式运行入口
- `scripts/runtime_bootstrap.py`：运行链路装配逻辑（供 run/test 复用）
- `voice/audio/hub.py`：音频输入与广播
- `voice/audio/recorder.py`：录音服务（定时 + VAD）
- `voice/wakeword/openwakeword_engine.py`：OpenWakeWord 适配
- `sylphos/voice/stt/`：SenseVoice / FunASR STT 模块
- `sylphos/voice/tts/`：CosyVoice TTS 模块
- `sylphos/runtime/events.py`：Runtime 事件定义
- `sylphos/runtime/stt_handler.py`：`recording.completed -> asr.completed`
- `sylphos/runtime/tts_handler.py`：`tts.requested -> tts.completed`
- `sylphos/runtime/orchestrator.py`：事件编排
- `download.py`：下载 openwakeword 模型

旧脚本（仍保留，主要用于历史/单点调试）：
- `test_openwakeword_win11.py`
- `voice/VAD/test_silero_vad.py`
- `detect_from_microphone.py`（示例脚本，额外依赖 `pyaudio`）

三、从零开始安装（Windows + 项目内 .venv）
----------------------------------------
```powershell
git clone git@github.com:shakamilo1/sylphos.git
cd sylphos
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

四、基础测试
-----------
```powershell
python -m compileall scripts voice sylphos config
python -m scripts.test_wakeword_pipeline --help
python -m scripts.test_wakeword_pipeline show-config
python -m scripts.test_wakeword_pipeline check-config
python -m scripts.test_wakeword_pipeline list-models
```

未找到 wakeword 模型时可运行：
```powershell
python download.py
```

五、录音/唤醒测试（可选）
----------------------
```powershell
python -m scripts.test_wakeword_pipeline test-timed-record --duration 3
python -m scripts.test_wakeword_pipeline test-vad-record --duration 12
python -m scripts.test_wakeword_pipeline test-full-pipeline --duration 20
```

六、SenseVoice / FunASR STT
--------------------------
STT 是正式模块，但依赖不并入主 `requirements.txt`。在 Python 3.12 环境中安装：
```powershell
pip install -r .\requirements-asr.txt
```

下载/初始化模型：
```powershell
python -m sylphos.voice.stt.healthcheck --download-only --device cpu
```

识别最新录音：
```powershell
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

Runtime 模拟 `RecordingCompleted -> ASRCompleted`：
```powershell
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

详细说明见 `docs/asr_sensevoice.md`。

七、CosyVoice TTS
----------------
TTS 是正式模块，但依赖不并入主 `requirements.txt`。`requirements-tts.txt` 只包含 Sylphos TTS 基础依赖，不包含 CosyVoice 本体。在 Python 3.12 环境中安装：
```powershell
pip install -r .\requirements-tts.txt
```

请按 CosyVoice 官方仓库在当前 Python 3.12 虚拟环境中从源码安装 CosyVoice；否则 healthcheck 会提示缺少 `cosyvoice`。

下载/初始化模型：
```powershell
python -m sylphos.voice.tts.healthcheck --download-only --device cpu
```

合成 wav：
```powershell
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output .\outputs\tts\latest_tts.wav --device cpu
```

JSON 输出：
```powershell
python -m sylphos.voice.tts.healthcheck --text "你好。" --json
```

Runtime 模拟 `TTSRequested -> TTSCompleted`：
```powershell
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

详细说明见 `docs/tts_cosyvoice.md`。

八、依赖分层说明
--------------
主链路直接依赖（已写入 `requirements.txt`）：
- `openwakeword`、`onnxruntime`
- `numpy`
- `sounddevice`
- `silero-vad`
- `scipy`（重采样回退路径）

可选依赖：
- STT：`requirements-asr.txt`
- TTS：`requirements-tts.txt`
- `samplerate`：重采样性能优化项；未安装时代码会自动回退到 `scipy`
- `soundfile`：旧脚本 `voice/VAD/test_silero_vad.py` 使用
- `pyaudio`：旧示例 `detect_from_microphone.py` 使用

九、模型与输出文件
----------------
- Wakeword 模型可通过 `python download.py` 下载。
- 自定义 wakeword 模型建议放在 `models/wakeword/`。
- TTS 模型建议放在 `models/tts/` 或使用 CosyVoice/ModelScope 默认缓存。
- 录音输出在 `recordings/` 下。
- TTS 输出在 `outputs/tts/` 下。
- 模型文件、缓存目录、输出音频不要提交 Git。

十、配置覆盖关系
--------------
配置加载顺序：
1) 先加载 `config/voice.py` 默认值
2) 若存在 `config/local_config.py`，同名配置覆盖默认值

十一、运行配置向导
----------------
```powershell
python -m scripts.setup_wakeword
```

向导会覆盖/写入 `config/local_config.py`，主要包含输入设备、采样率、声道、blocksize、dtype、wakeword 模型来源、阈值、冷却时间、录音目录、定时录音参数和 VAD 配置。
