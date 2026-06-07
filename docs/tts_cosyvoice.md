# Sylphos 正式 TTS（CosyVoice）

本文说明 Sylphos 正式 TTS 模块、CosyVoice 健康检查入口，以及 Runtime EventBus 模拟流程。

> 如需在 WSL2 上部署 CosyVoice3 FastAPI 服务，并由 Windows Sylphos 主程序调用，请参考 [CosyVoice3 WSL2/Windows 部署文档](./cosyvoice3_wsl2_windows_deployment.md)。

## 1) Python 3.12 环境

```powershell
cd H:\sylphos1\sylphos
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r .\requirements-tts.txt
```

> 说明：`requirements-tts.txt` 只安装 Sylphos TTS 基础依赖（如 `torch`、`torchaudio`、`modelscope`、`numpy`），**不包含 CosyVoice 本体**。用户必须先按 CosyVoice 官方仓库说明，在同一个 Python 3.12 虚拟环境中从源码安装 `cosyvoice` 包；否则 healthcheck 会提示缺少 `cosyvoice`。

## 2) 下载/初始化模型

```powershell
python -m sylphos.voice.tts.healthcheck --download-only --device cpu
```

`--download-only` 的语义是：实例化/加载 `CosyVoiceEngine`，从而触发 CosyVoice 自身的模型初始化或下载逻辑。Sylphos 不在这里实现额外的 `snapshot_download` 下载器，也不提交任何模型文件。

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

Runtime 模拟也支持 zero-shot 参数透传：

```powershell
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --prompt-wav .\prompt.wav --prompt-text "参考音频文本" --json
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
- `requirements-tts.txt`：Sylphos TTS 基础依赖，不并入主 `requirements.txt`，也不包含 CosyVoice 本体。

## 8) 常见问题

### 缺少 CosyVoice 依赖

健康检查会明确提示：`requirements-tts.txt` 不包含 CosyVoice 本体。请按 CosyVoice 官方源码安装步骤，在当前 Python 3.12 环境中安装 `cosyvoice` 包。

### 模型加载失败

常见原因：模型未下载、网络问题、Python 3.12 / Torch / CUDA 版本不兼容、模型目录路径错误或缺少模型配置文件。

### GPU/CPU

`CosyVoiceEngine` 正式默认 `device="gpu"`；健康检查默认 `--device cpu`，方便在没有 CUDA 的 Windows 机器上先验证依赖和模型下载流程。
