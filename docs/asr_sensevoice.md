# Sylphos 正式 ASR（SenseVoice）

本文说明 SenseVoice STT 在 Sylphos 中的独立验证与 Runtime 事件总线集成方式。

## 1) 安装环境（Windows + PowerShell）
项目正式 Python 版本为 **Python 3.12**。

```powershell
# 创建独立 venv
cd <repo-root>
py -3.12 -m venv .venv-asr
.\.venv-asr\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\requirements-asr.txt
```


> 依赖说明：`requirements-asr.txt` 已将 `editdistance` 替换为纯 Python 库 `textdistance`。
> 在 **Python 3.12 + Windows** 环境下可直接安装，无需编译 `editdistance` 的 C++ 扩展（该扩展在该环境下可能编译失败）。
> 文档中的安装与健康检查命令保持不变。

## 2) 模型下载与预热
```powershell
# 仅加载模型（可视为下载/初始化）
python -m sylphos.voice.stt.healthcheck --download-only --device cpu

# 使用指定 wav 预热
python -m sylphos.voice.stt.healthcheck --warmup .\recordings\latest_command.wav --device cpu --language zh
```

## 3) 识别最新录音 / 指定 wav
```powershell
# 识别 latest_command.wav
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh

# 识别指定 wav
python -m sylphos.voice.stt.healthcheck --audio .\recordings\latest_command.wav --device cpu --language zh
```

## 4) 系统接入（Runtime EventBus）

### 4.1 事件总线类型
- `recording.completed`：录音结束事件（携带 `wav_path`、`sample_rate`）。
- `asr.completed`：识别完成事件（携带 `audio_path`、`text`、`raw_text`、`language`、`metadata`）。

### 4.2 接入方式
- `VoiceController.on_record_complete()` 不再直接调用 STT，而是发布 `RecordingCompleted`。
- `runtime/stt_handler.py` 监听 `recording.completed`，内部通过 `create_stt_engine()` 调用 SenseVoice。
- 识别成功后发布 `ASRCompleted`，供下游 NLU/Agent 消费。

### 4.3 Runtime 一体化验证
```powershell
# 识别最新录音并通过事件总线触发
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

JSON 输出新增：
- `event_published: bool`：是否成功发布 `asr.completed`。
- `events: list[dict]`：采集到的事件列表，便于调试事件流。

## 5) VoiceController 触发说明
- 保持 wakeword -> recorder -> VAD 原流程不变。
- 仅在录音完成回调节点增加事件发布，实现 STT 模块化替换。
- 未来替换 Whisper/其他引擎时，仅需扩展 `factory.py` 与具体 engine，不改控制器主流程。

## 6) 字段说明（ASR 结果）
- `text`: 规范化后的识别文本（推荐用于下游指令理解）。
- `raw_text`: 原始输出文本（用于回溯或调试）。
- `language`: 识别语言（auto/zh/en/...）。
- `metadata`: 引擎附加信息（模型、耗时、分段信息等）。

## 7) 错误与调试方法
- 若依赖失败（`funasr` / `torch` / `modelscope`），先执行：
  - `python -m pip install --upgrade pip setuptools wheel`
  - `pip install -r .\requirements-asr.txt --verbose`
- 如果 Runtime 测试中 `event_published=false`：
  1. 检查 `audio_path` 是否存在；
  2. 开启 `--debug` 查看异常信息；
  3. 检查模型和设备参数是否可用（如 `--device cpu`）。
