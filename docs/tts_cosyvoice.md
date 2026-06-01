# Sylphos 正式 TTS（CosyVoice）

本文说明 Sylphos 正式 TTS 模块、CosyVoice 健康检查入口，以及 Runtime EventBus 模拟流程。

## 1) Python 3.12 环境

```powershell
cd H:\sylphos1\sylphos
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\requirements-tts.txt
```

> 说明：CosyVoice 通常需要按其官方仓库从源码安装。如果 `pip install -r .\requirements-tts.txt` 后仍提示缺少 `cosyvoice` 模块，请先在同一个 Python 3.12 虚拟环境中完成 CosyVoice 源码安装，再回到 Sylphos 运行健康检查。

## 2) 下载/初始化模型

```powershell
python -m sylphos.voice.tts.healthcheck --download-only --device cpu
```

可通过 `--model` 指定远程模型名或本地模型目录，例如：

```powershell
python -m sylphos.voice.tts.healthcheck --download-only --model .\models\tts\CosyVoice3-0.5B --device cpu
```

## 3) 合成一句话

```powershell
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output .\outputs\tts\latest_tts.wav --device cpu
```

输出目录会自动创建。模型文件、缓存目录和输出音频不要提交 Git。

## 4) JSON 输出

```powershell
python -m sylphos.voice.tts.healthcheck --text "你好。" --json
```

JSON 至少包含 `ok`、`python`、`cwd`、`project_root`、`model`、`device`、`text`、`output_path`、`elapsed_seconds`、`dependencies_ok`、`dependency_errors` 和 `errors`。

## 5) Runtime 模拟

```powershell
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

该命令会模拟：

1. 创建 `EventBus`。
2. 启动 `TTSHandler` 并订阅 `tts.requested`。
3. 发布 `TTSRequested`。
4. `TTSHandler` 调用 `create_tts_engine()` 和 `CosyVoiceEngine.synthesize_to_file()`。
5. 合成成功后发布 `TTSCompleted`。

## 6) 模块定位

- 当前是正式 TTS 模块和健康检查入口。
- 当前不自动接入完整对话流程。
- 后续由 LLM/Orchestrator 发布 `TTSRequested`，再由 `TTSHandler` 合成语音。
- 不要把 TTS 硬塞进 `VoiceController`。

## 7) 目录与文件

- `sylphos/voice/tts/base.py`：统一 TTS 协议与 `TTSResult`。
- `sylphos/voice/tts/cosyvoice.py`：CosyVoice 引擎适配器，支持 CosyVoice3 优先、本地目录或远程模型名、WAV 输出。
- `sylphos/voice/tts/factory.py`：TTS 工厂。
- `sylphos/voice/tts/healthcheck.py`：唯一 TTS 健康检查入口。
- `sylphos/runtime/tts_handler.py`：Runtime EventBus TTS 处理器。
- `requirements-tts.txt`：TTS 可选依赖，不并入主 `requirements.txt`。

## 8) 常见问题

### 缺少 CosyVoice 依赖

健康检查会提示安装 `requirements-tts.txt`。如果仍缺少 `cosyvoice`，请按 CosyVoice 官方源码安装步骤在当前 Python 3.12 环境中安装。

### 模型加载失败

常见原因：模型未下载、网络问题、Python 3.12 / Torch / CUDA 版本不兼容、模型目录路径错误或缺少模型配置文件。

### GPU/CPU

`CosyVoiceEngine` 正式默认 `device="gpu"`；健康检查默认 `--device cpu`，方便在没有 CUDA 的 Windows 机器上先验证依赖和模型下载流程。
