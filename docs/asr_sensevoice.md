# Sylphos 正式 ASR（SenseVoice）

## 环境建议（Windows + PowerShell）
推荐 Python 3.12。

```powershell
cd H:\sylphos
py -3.12 -m venv .venv-asr
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

## 当前阶段说明
- 这是正式 ASR 模块和集中式健康检查入口。
- 暂不自动接入 VoiceController。
- 下一步可以在 `VoiceController.on_record_complete()` 中调用 `stt_engine.transcribe_file(wav_path)`。
- 未来 Runtime 版本建议通过 EventBus 发布 `RecordingCompleted` 和 `ASRCompleted` 事件。
