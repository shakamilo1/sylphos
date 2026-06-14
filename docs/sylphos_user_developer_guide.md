# Sylphos 用户 / 开发者指导手册

> 适用对象：希望在本地部署、调试、二次开发 Sylphos Runtime 的用户和开发者。本文按“先跑通 dummy 链路，再逐步接入真实 WakeWord、ASR、ToolExecutor、TTS”的顺序组织。

## 1. 项目简介

Sylphos 是一个事件驱动的本地智能 Runtime，用于把语音输入、文本输入、LLM/路由、工具执行、语音/界面输出组织成可观察、可打断、可恢复的流水线。

核心链路如下：

```text
WakeWord → 录音 → ASR → LLM/路由 → ToolExecutor → TTS/UI
```

Sylphos 的设计目标不是把所有模块硬编码成一条不可变流程，而是把每一步都建模为 Runtime 事件和状态迁移，因此支持：

- 任意模块手动切入、切出、跳转、重试或跳过。
- 使用控制台命令注入事件，便于在没有真实麦克风、ASR、TTS 或工具执行器时测试 Runtime。
- ToolExecutor 支持 `dummy` 与 `openclaw` 两类 provider：
  - `dummy`：用于最小闭环测试，不实际操作外部系统。
  - `openclaw`：用于连接 OpenClaw CLI / SDK / API，支持 dry-run 与真实执行。
- STT 支持 `SenseVoice` 与 `DummySTT`：
  - `SenseVoice`：用于真实中文/多语种 ASR。
  - `dummy`：用于跳过模型依赖，直接验证 Runtime 事件链路。
- TTS 支持 `CosyVoice` 与 `DummyTTS`：
  - `CosyVoice`：可通过本地模块或 FastAPI 服务接入真实语音合成。
  - `dummy`：用于只打印文本、不合成音频的调试场景。

推荐调试顺序：

1. 先使用 `dummy` STT/TTS 和 dry-run ToolExecutor 验证 Runtime。
2. 再启用 OpenClaw dry-run，确认请求、日志、UI/TTS 输出都符合预期。
3. 最后接入真实 OpenClaw、WakeWord、Recorder、SenseVoice、CosyVoice。

## 2. 依赖和安装

### 2.1 基础环境

Sylphos 推荐使用 Python 3.12 和项目内虚拟环境运行。

Windows PowerShell 示例：

```powershell
git clone <your-sylphos-repo-url> sylphos
cd sylphos
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Linux / macOS 示例：

```bash
git clone <your-sylphos-repo-url> sylphos
cd sylphos
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### 2.2 WakeWord 依赖

WakeWord 依赖通常包含：

- `openWakeWord`
- `onnxruntime`
- `numpy`
- 音频输入相关依赖，例如 `sounddevice`

如果 `requirements.txt` 已包含这些包，直接安装主依赖即可。若需要单独补装，可执行：

```powershell
pip install openwakeword onnxruntime sounddevice numpy
```

### 2.3 STT：SenseVoice / DummySTT

- `STT_PROVIDER = "dummy"`：无需额外模型，适合先跑通 Runtime。
- `STT_PROVIDER = "SenseVoice"`：需要安装 SenseVoice / FunASR 相关依赖，并准备模型缓存。

如项目提供 ASR 依赖文件，可执行：

```powershell
pip install -r requirements-asr.txt
```

建议先运行项目内 STT 健康检查或最小识别脚本，确认模型可下载、可加载、可推理后，再接入 Runtime。

### 2.4 TTS：CosyVoice / DummyTTS

- `TTS_PROVIDER = "dummy"`：不合成音频，只输出文本，适合 Runtime 调试。
- `TTS_PROVIDER = "CosyVoice"`：可接入本地 CosyVoice 或 CosyVoice3 FastAPI 服务。

如项目提供 TTS 依赖文件，可执行：

```powershell
pip install -r requirements-tts.txt
```

CosyVoice3 FastAPI 服务是可选项。如果希望 Sylphos 通过 HTTP 调用 CosyVoice3，请先启动服务，并在配置中设置：

```python
COSYVOICE_URL = "http://127.0.0.1:8000"
```

### 2.5 OpenClaw CLI / SDK / API

OpenClaw 是 Sylphos 的可选 ToolExecutor 后端。根据你的接入方式准备以下一种或多种能力：

- OpenClaw CLI：适合本地命令行调用与 dry-run / 真实执行验证。
- OpenClaw SDK：适合在 Python 进程内直接调用。
- OpenClaw API / Gateway：适合通过 HTTP 或 WebSocket 连接外部服务。

Windows 下建议确认 CLI 已安装，并能在 PowerShell 中执行：

```powershell
openclaw --help
```

如果 CLI 不在 `PATH` 中，可以在 `local_config.py` 中指定完整路径，例如：

```python
OPENCLAW_CLI_PATH = r"C:\Users\shakamilo\AppData\Roaming\npm\openclaw.cmd"
```

## 3. 配置示例：`config/local_config.py`

下面是一份可直接复制覆盖的 `config/local_config.py` 样例。首次使用建议先保持 `OPENCLAW_DRY_RUN = True`，并将 `STT_PROVIDER` / `TTS_PROVIDER` 设置为 `dummy` 来验证 Runtime。

```python
# AUDIO 配置
AUDIO_ENABLED = True
AUDIO_INPUT_DEVICE_NAME = "麦克风 (BOYA mini)"
INPUT_RATE = 44100
CHANNELS = 1
BLOCKSIZE = 4410
DTYPE = "float32"

# WAKEWORD 配置
WAKEWORD_MODEL_SOURCE = "project_relative"
WAKEWORD_MODEL_DIR = "models/wakeword"
WAKEWORD_MODEL_NAME = "hey_jarvis_v0.1.onnx"
WAKEWORD_THRESHOLD = 0.5
WAKEWORD_COOLDOWN_SECONDS = 2.0

# STT/TTS 配置
STT_PROVIDER = "SenseVoice"  # 或 "dummy" 先测试
TTS_PROVIDER = "dummy"
COSYVOICE_URL = "http://127.0.0.1:8000"

# ToolExecutor 配置
TOOL_EXECUTOR_PROVIDER = "openclaw"
OPENCLAW_MODE = "cli"
OPENCLAW_DRY_RUN = True
OPENCLAW_CLI = "openclaw"
OPENCLAW_CLI_PATH = r"C:\Users\shakamilo\AppData\Roaming\npm\openclaw.cmd"
OPENCLAW_TIMEOUT_SECONDS = 120
```

### 3.1 推荐配置组合

| 场景 | STT | TTS | ToolExecutor | 说明 |
| --- | --- | --- | --- | --- |
| 最小 Runtime 调试 | `dummy` | `dummy` | `dummy` | 不依赖模型和外部工具。 |
| OpenClaw dry-run | `dummy` | `dummy` | `openclaw` + `OPENCLAW_DRY_RUN=True` | 验证路由、日志、UI/TTS 输出。 |
| 真实工具执行 | `dummy` 或 `SenseVoice` | `dummy` 或 `CosyVoice` | `openclaw` + `OPENCLAW_DRY_RUN=False` | 会真实调用 OpenClaw。 |
| 完整语音链路 | `SenseVoice` | `CosyVoice` | `openclaw` | WakeWord、录音、ASR、工具执行、TTS 全部启用。 |

### 3.2 配置检查清单

启动 Runtime 前建议逐项确认：

- `AUDIO_INPUT_DEVICE_NAME` 与系统麦克风名称一致。
- `WAKEWORD_MODEL_DIR / WAKEWORD_MODEL_NAME` 指向的 `.onnx` 文件真实存在。
- `STT_PROVIDER` 与 `TTS_PROVIDER` 的大小写和代码实现一致。
- `OPENCLAW_DRY_RUN` 是否符合当前测试目标。
- `OPENCLAW_CLI_PATH` 在 Windows 中建议使用 raw string：`r"..."`。
- 若使用 CosyVoice3 FastAPI，`COSYVOICE_URL` 指向正在运行的服务。

## 4. WakeWord 模型下载

### 4.1 使用 openWakeWord 自带下载函数

进入项目虚拟环境后执行：

```powershell
python -c "from openwakeword.utils import download_models; download_models()"
```

该命令会下载 openWakeWord 官方资源模型到 Python 包资源目录。下载完成后，可先确认包内模型列表：

```powershell
python -c "import importlib.resources as ir; from pathlib import Path; p=Path(str(ir.files('openwakeword')/'resources'/'models')); print([x.name for x in p.glob('*.onnx')])"
```

### 4.2 放置项目自定义模型

如果 `local_config.py` 使用如下配置：

```python
WAKEWORD_MODEL_SOURCE = "project_relative"
WAKEWORD_MODEL_DIR = "models/wakeword"
WAKEWORD_MODEL_NAME = "hey_jarvis_v0.1.onnx"
```

则需要确保项目目录下存在：

```text
models/wakeword/hey_jarvis_v0.1.onnx
```

可用 PowerShell 检查：

```powershell
Test-Path .\models\wakeword\hey_jarvis_v0.1.onnx
```

Linux / macOS 可用：

```bash
test -f ./models/wakeword/hey_jarvis_v0.1.onnx && echo ok
```

### 4.3 模型不存在时的预期行为

如果配置指定的模型不存在，WakeWord 启动应给出清晰错误，提示缺失的模型路径。Sylphos 不应静默回退到 `alexa_v0.1.onnx`，因为静默回退会导致“配置看似正确、实际唤醒词不一致”的调试问题。

## 5. 运行 Sylphos Runtime

确保已激活虚拟环境并完成配置后，执行：

```powershell
python run_sylphos_runtime.py
```

建议首次运行时使用保守配置：

```python
STT_PROVIDER = "dummy"
TTS_PROVIDER = "dummy"
TOOL_EXECUTOR_PROVIDER = "openclaw"
OPENCLAW_DRY_RUN = True
```

这样可以先确认 Runtime、事件总线、OpenClaw 请求封装、TTS/UI 输出链路正常，再逐步打开真实音频、真实 ASR、真实 TTS、真实工具执行。

启动成功后，控制台会进入交互模式，可以输入 `help` 查看命令列表。

## 6. 控制台命令

Runtime 控制台命令用于在不依赖真实外设或模型的情况下手动注入事件、切换状态、验证局部模块。

| 命令 | 作用 | 示例 |
| --- | --- | --- |
| `q` | 退出 Runtime。 | `q` |
| `w` | 模拟 `WakeWordDetected`。 | `w` |
| `r` | 恢复唤醒监听。 | `r` |
| `p` | 暂停唤醒监听。 | `p` |
| `c` | 取消当前任务。 | `c` |
| `t 文本` | 发布 `TextInputReceived`。 | `t 打开浏览器` |
| `asr 文本` | 发布 `ASRCompleted`。 | `asr 打开浏览器` |
| `utt 文本` | 发布 `UserUtteranceReady`。 | `utt 打开浏览器` |
| `tts 文本` | 发布 `TTSRequested`。 | `tts 你好，我是 Sylphos` |
| `exec 工具名 参数JSON` | 发布 `ToolExecutionRequested`。 | `exec openclaw {"command":"打开浏览器"}` |
| `state` | 打印 `RuntimeContext`。 | `state` |
| `jump 状态名` | 发布 `RuntimeJumpRequested`。 | `jump IDLE` |
| `retry 步骤名` | 发布 `StepRetryRequested`。 | `retry ASR` |
| `skip 步骤名` | 发布 `StepSkipped`。 | `skip TTS` |
| `help` | 显示帮助。 | `help` |

### 6.1 常用手动事件流程

手动模拟文本输入到工具执行：

```text
t 打开浏览器
exec openclaw {"command":"打开浏览器"}
```

手动绕过录音和 ASR，直接发布 ASR 结果：

```text
asr 打开浏览器
```

手动测试 TTS 输出：

```text
tts 你好，我是 Sylphos。
```

查看当前 Runtime 状态：

```text
state
```

遇到错误状态后，可尝试跳转、重试或跳过：

```text
jump IDLE
retry ToolExecutor
skip TTS
```

## 7. 测试步骤

### 7.1 Dummy 执行器测试

目标：确认 Runtime 事件链路可用，不依赖真实 OpenClaw。

推荐配置：

```python
STT_PROVIDER = "dummy"
TTS_PROVIDER = "dummy"
TOOL_EXECUTOR_PROVIDER = "dummy"
```

启动 Runtime：

```powershell
python run_sylphos_runtime.py
```

在控制台输入：

```text
t 打开浏览器
exec openclaw {"command":"打开浏览器"}
```

预期结果：

- 控制台显示文本输入事件已发布。
- ToolExecutor 返回 dummy 结果或模拟执行结果。
- Runtime 不应因缺少 OpenClaw、SenseVoice、CosyVoice 而退出。
- 如启用 UI/TTS 输出，应能看到对应文本输出。

### 7.2 OpenClaw dry-run

目标：验证 OpenClaw executor 的请求构造、路由、日志、TTS/UI 输出，但不真实执行外部操作。

确保配置如下：

```python
TOOL_EXECUTOR_PROVIDER = "openclaw"
OPENCLAW_MODE = "cli"
OPENCLAW_DRY_RUN = True
```

启动 Runtime：

```powershell
python run_sylphos_runtime.py
```

在控制台输入：

```text
t 打开浏览器
```

预期结果：

- 输出显示 OpenClaw dry-run 执行。
- 不会真实打开浏览器或操作系统应用。
- 应能看到 ToolExecutionCompleted 或等价的模拟完成事件。
- TTS/UI 应输出适合用户阅读的简短结果，而不是完整日志。

### 7.3 真实 OpenClaw 执行

目标：真实调用 OpenClaw 执行工具请求。

执行前确认：

- OpenClaw CLI / SDK / API 已安装并可用。
- `OPENCLAW_CLI_PATH` 或 `OPENCLAW_CLI` 指向正确命令。
- 当前请求是安全、可执行、可回滚或风险可接受的。

配置：

```python
TOOL_EXECUTOR_PROVIDER = "openclaw"
OPENCLAW_MODE = "cli"
OPENCLAW_DRY_RUN = False
```

启动 Runtime：

```powershell
python run_sylphos_runtime.py
```

在控制台输入：

```text
exec openclaw {"command":"打开浏览器"}
```

检查项：

- 是否收到 `ToolExecutionCompleted` 或 `ToolExecutionFailed`。
- `stdout`、`stderr`、退出码、超时信息是否清晰。
- TTS/UI 是否给出简短、可理解的执行反馈。
- 审计日志或运行日志是否记录了请求与结果。

### 7.4 真实音频 + WakeWord + Recorder

目标：验证真实麦克风输入、WakeWord 模型加载、唤醒后录音链路。

配置：

```python
AUDIO_ENABLED = True
AUDIO_INPUT_DEVICE_NAME = "麦克风 (BOYA mini)"
WAKEWORD_MODEL_SOURCE = "project_relative"
WAKEWORD_MODEL_DIR = "models/wakeword"
WAKEWORD_MODEL_NAME = "hey_jarvis_v0.1.onnx"
```

启动 Runtime：

```powershell
python run_sylphos_runtime.py
```

测试方式：

1. 先输入 `w` 模拟唤醒，确认 Runtime 能进入录音或后续状态。
2. 再说真实唤醒词，确认 `hey_jarvis_v0.1.onnx` 被加载并参与推理。
3. 观察录音是否开始、是否正常结束、是否发布录音完成事件。
4. 如果后续 ASR 还未准备好，可先把 `STT_PROVIDER` 设置为 `dummy`，只验证 WakeWord + Recorder。

预期结果：

- Runtime 启动时打印或记录加载的 WakeWord 模型路径。
- 模型路径应是 `models/wakeword/hey_jarvis_v0.1.onnx`，而不是默认的 `alexa_v0.1.onnx`。
- 模型不存在时应报出清晰错误。
- 麦克风权限、采样率、声道数异常时应有可定位的错误信息。

## 8. 注意事项

### 8.1 配置和模型路径

- 确认 `config/local_config.py` 中的模型路径存在。
- 自定义唤醒词模型建议统一放在 `models/wakeword/`。
- 不要把大型模型文件、缓存目录、录音输出、TTS 输出提交到 Git。
- Windows 路径建议使用 raw string，例如 `r"C:\path\to\file"`。

### 8.2 分阶段接入真实模块

初次使用建议先设置：

```python
STT_PROVIDER = "dummy"
TTS_PROVIDER = "dummy"
OPENCLAW_DRY_RUN = True
```

这样可以先测试 Runtime 主链路，避免同时排查音频设备、模型下载、GPU/CPU 推理、OpenClaw 调用等多个问题。

### 8.3 OpenClaw 可用性

- 确认 OpenClaw CLI / SDK 已安装并在 `PATH` 可用。
- 如果不在 `PATH`，请设置 `OPENCLAW_CLI_PATH`。
- 开启真实执行前，务必将 `OPENCLAW_DRY_RUN` 从 `True` 改为 `False`，并确认请求风险。
- 真实执行失败时优先检查命令路径、权限、网络、认证、超时配置。

### 8.4 WakeWord 模型回退策略

如果模型不存在，WakeWord 启动应报清晰错误，而不会默认加载 `alexa_v0.1.onnx`。请优先修正：

- `WAKEWORD_MODEL_SOURCE`
- `WAKEWORD_MODEL_DIR`
- `WAKEWORD_MODEL_NAME`
- 模型文件是否实际存在

### 8.5 音频设备问题

如果无法录音或无法检测唤醒词：

- 检查系统麦克风权限。
- 检查设备名称是否与 `AUDIO_INPUT_DEVICE_NAME` 完全匹配。
- 检查采样率 `INPUT_RATE` 是否被设备支持。
- 尝试降低 `BLOCKSIZE` 或改用默认输入设备。
- 先用控制台 `w` 命令模拟唤醒，判断问题是否只出在真实音频输入。

## 9. 目录结构参考

```text
sylphos/
├─ config/
│   ├─ defaults.py
│   ├─ loader.py
│   └─ local_config.py
├─ runtime/
├─ executor/
├─ voice/
│   ├─ wakeword/
│   ├─ audio/
│   ├─ stt/
│   └─ tts/
├─ frontend/
└─ run_sylphos_runtime.py
```

当前仓库可能仍处于快速迭代阶段，实际目录名可能带有包名前缀或拆分为多个顶层目录。若文件位置不同，请以项目当前代码为准，但建议保持以下职责边界：

- `config/`：默认配置、本地覆盖配置、配置加载逻辑。
- `runtime/`：事件、状态、上下文、调度、控制台命令。
- `executor/`：ToolExecutor 抽象、dummy executor、OpenClaw executor。
- `voice/wakeword/`：openWakeWord 引擎封装与模型加载。
- `voice/audio/`：麦克风输入、音频分发、录音器。
- `voice/stt/`：SenseVoice / DummySTT。
- `voice/tts/`：CosyVoice / DummyTTS。
- `frontend/`：桌面 UI、侧边栏、Web UI 或其他展示层。

## 10. 推荐从零验证流程

如果你刚拉取项目，推荐按下面顺序验证：

1. 创建并激活 Python 3.12 venv。
2. 安装 `requirements.txt`。
3. 复制第 3 节的 `config/local_config.py`，但先把 `STT_PROVIDER` 和 `TTS_PROVIDER` 改为 `dummy`。
4. 下载或放置 WakeWord 模型。
5. 运行 `python run_sylphos_runtime.py`。
6. 输入 `help` 查看控制台命令。
7. 输入 `t 打开浏览器` 验证文本事件。
8. 输入 `exec openclaw {"command":"打开浏览器"}` 验证 ToolExecutor dry-run。
9. 输入 `w` 验证模拟唤醒。
10. 设置 `AUDIO_ENABLED=True` 后验证真实麦克风和 WakeWord。
11. 接入 SenseVoice，验证 ASR。
12. 接入 CosyVoice 或 CosyVoice3 FastAPI，验证 TTS。
13. 最后将 `OPENCLAW_DRY_RUN=False`，验证真实 OpenClaw 执行。

## 11. 常见问题排查

### 11.1 启动时报找不到 WakeWord 模型

检查：

```powershell
Test-Path .\models\wakeword\hey_jarvis_v0.1.onnx
```

如果返回 `False`，请下载模型或修正 `WAKEWORD_MODEL_DIR` / `WAKEWORD_MODEL_NAME`。

### 11.2 控制台命令可以跑，真实唤醒不触发

通常说明 Runtime 主链路正常，问题集中在音频输入或 WakeWord：

- 麦克风设备名不匹配。
- 系统权限未开启。
- 采样率或声道配置不被设备支持。
- 模型文件不是当前唤醒词。
- 阈值 `WAKEWORD_THRESHOLD` 过高。

### 11.3 OpenClaw dry-run 正常，真实执行失败

检查：

```powershell
openclaw --help
```

以及：

```powershell
where openclaw
```

常见原因：

- CLI 未安装或不在 `PATH`。
- `OPENCLAW_CLI_PATH` 配置错误。
- 认证或网络不可用。
- 请求超时，需调大 `OPENCLAW_TIMEOUT_SECONDS`。
- OpenClaw 拒绝高风险操作，需要确认或修改策略。

### 11.4 TTS 没有声音

若 `TTS_PROVIDER = "dummy"`，没有真实音频输出是预期行为。若使用 CosyVoice：

- 确认 CosyVoice 模型已下载。
- 确认 CosyVoice3 FastAPI 服务已启动。
- 确认 `COSYVOICE_URL` 正确。
- 检查输出 wav 是否生成。
- 检查系统音频播放设备。

### 11.5 ASR 没有结果

若 `STT_PROVIDER = "dummy"`，真实语音不会进入模型识别。若使用 SenseVoice：

- 确认 ASR 依赖已安装。
- 确认模型可加载。
- 确认录音文件真实存在且非静音。
- 先用单独 healthcheck 或脚本识别 wav，再接入 Runtime。

## 12. 开发者扩展建议

### 12.1 新增 ToolExecutor

建议接口保持来源无关：输入使用结构化请求，输出包含：

- `success` / `failed` 状态。
- 可给用户朗读的 `speak_text`。
- 可给 UI 展示的 `ui_text`。
- 原始输出、错误输出、退出码、耗时、审计信息。

### 12.2 新增 STT Provider

建议最小实现：

- 输入录音文件路径或音频 buffer。
- 输出标准化文本、语言、置信度、耗时。
- 出错时返回清晰异常或失败事件。

### 12.3 新增 TTS Provider

建议最小实现：

- 输入待播报文本。
- 输出音频文件路径、播放状态或 dummy 文本结果。
- 对长文本做截断或摘要，避免把工具日志全文读出来。

### 12.4 Runtime 事件调试

新增模块时建议先支持控制台手动事件注入。例如：

- 用 `t 文本` 绕过 WakeWord 和 ASR。
- 用 `asr 文本` 绕过录音和 ASR 模型。
- 用 `tts 文本` 单测 TTS。
- 用 `exec 工具名 参数JSON` 单测 ToolExecutor。
- 用 `jump` / `retry` / `skip` 验证异常恢复。
