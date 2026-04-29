# Sylphos 正式 ASR（SenseVoice）

## 环境建议（Windows + PowerShell）
项目正式 Python 版本要求为 **Python 3.13**。

```powershell
cd H:\sylphos
py -3.13 -m venv .venv-asr
.\.venv-asr\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\requirements-asr.txt
```

## 下载 / 加载模型
```powershell
python -m sylphos.voice.stt.healthcheck --download-only --device cpu
```

## 识别最新录音
```powershell
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

## 识别指定 wav
```powershell
python -m sylphos.voice.stt.healthcheck --audio .\recordings\latest_command.wav --device cpu --language zh
```

## 预热模型
```powershell
python -m sylphos.voice.stt.healthcheck --warmup .\recordings\latest_command.wav --device cpu --language zh
```

## 依赖兼容性排查（Python 3.13）
- 如果 `funasr`、`torch`、`modelscope` 在 Python 3.13 下安装失败，请先升级 pip/setuptools/wheel 后重试。
- 如果仍失败，请记录完整报错（含包名和版本）并在项目中反馈；不要降低项目 Python 版本。
- 可优先尝试：
  - `python -m pip install --upgrade pip setuptools wheel`
  - `pip install -r .\requirements-asr.txt --verbose`

## 当前阶段说明
- 这是正式 ASR 模块和集中式健康检查入口。
- 暂不自动接入 VoiceController。
- 下一步可以在 `VoiceController.on_record_complete()` 中调用 `stt_engine.transcribe_file(wav_path)`。
- 未来 Runtime 版本建议通过 EventBus 发布 `RecordingCompleted` 和 `ASRCompleted` 事件。
