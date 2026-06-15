# Sylphos 使用手册：最小运行路径与推荐模块接入

## 1. 这份手册适合谁

本手册面向第一次部署或使用 Sylphos 的普通用户，目标是按最短路径跑通当前可用能力。

- 适合想快速启动 Sylphos Runtime、OpenClaw、SenseVoice 或 CosyVoice3 的用户。
- 不覆盖完整开发细节、模型训练原理或所有内部实现。
- 命令尽量集中、可复制；检查和排错统一放在最后。
- 如果需要完整模块细节，请继续阅读对应专题文档，例如 `docs/asr_sensevoice.md`、`docs/tts_cosyvoice.md` 和 `docs/openclaw_integration.md`。

## 2. Sylphos 当前能做什么

Sylphos 是一个本地自然语言交互与计算机控制系统。当前可用方式包括：

- 通过控制台文本或语音链路接收输入。
- 通过 Sylphos Runtime 传递事件、调度模块和维护运行状态。
- 接入 OpenClaw 进行文本理解、任务处理、工具规划或本地控制桥接。
- 接入 SenseVoice / STT，将音频文件转换为文本。
- 接入 CosyVoice3 / TTS，将回复文本转换为语音文件或播放输出。
- 通过 Executor 执行受控的本地命令、本地 API、桌面控制或插件动作。

Sylphos 的设计仍然是模块化、事件驱动、可替换、可扩展的。最小组合可以按“输入 → Runtime → STT / OpenClaw / Executor / TTS → 输出”理解，但不应把任一模块写死为唯一入口或唯一后端。

当前仓库尚未提供单命令完整语音闭环启动器；建议先按模块分别跑通，再逐步组合。

## 3. 推荐使用路径

### 路径 A：最小文本路径

**用途**

- 不依赖麦克风。
- 不依赖 STT。
- 不依赖 TTS。
- 用于确认 Sylphos Runtime 和 OpenClaw 文本链路。

**运行方式**

启动 Sylphos Runtime：

```bash
python run_sylphos_runtime.py
```

进入提示符后输入文本事件：

```text
t 你好，介绍一下 Sylphos
```

也可以直接运行 OpenClaw 文本测试脚本：

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
```

### 路径 B：语音识别路径

**用途**

- 从麦克风录音。
- 生成 `recordings/latest_command.wav`。
- 调用 SenseVoice 将音频转换为文本。

**运行方式**

启动 wakeword + recorder 音频链路：

```bash
python scripts/run_wakeword_pipeline.py
```

录音文件生成后，调用 SenseVoice / STT：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

当前 `sylphos.voice.stt.healthcheck` 同时承担最小验证和手动调用用途；如果使用 Runtime 事件总线模式，可以运行：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

### 路径 C：语音合成路径

**用途**

- 输入一段文本。
- 调用 TTS。
- 生成 wav 文件。
- 可选播放输出。

**运行方式**

```bash
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output outputs/tts/latest_tts.wav --device cpu
```

如果要通过 Runtime 事件总线模拟 TTS 请求：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

### 路径 D：推荐完整组合路径

当前推荐组合是：

```text
文本 / 唤醒输入
  → Sylphos Runtime
  → SenseVoice / STT
  → OpenClaw
  → Executor
  → CosyVoice3 / TTS
  → 文本或语音输出
```

当前仓库尚未提供单命令完整闭环启动器，建议先按路径 A、B、C 分别跑通，再逐步接入 OpenClaw bridge、Executor 和 TTS 事件链路。

## 4. 使用前准备

只准备本次要用到的部分即可：

- **Python**：项目当前最低 Python 版本为 Python 3.12。
- **基础依赖**：运行 Sylphos Runtime 和通用模块时使用 `requirements.txt`。
- **OpenClaw**：需要文本理解、任务处理或工具规划时准备 OpenClaw CLI、HTTP 或 WebSocket 服务。
- **SenseVoice**：需要语音识别时安装 `requirements-asr.txt` 并准备模型缓存。
- **CosyVoice3**：需要语音合成时安装 `requirements-tts.txt`，并按 CosyVoice / CosyVoice3 要求准备依赖与模型。
- **麦克风**：仅在使用 wakeword、录音或 STT 语音输入路径时需要。

## 5. 启动 Sylphos Runtime

命令：

```bash
python run_sylphos_runtime.py
```

进入 `sylphos>` 提示符后，常用输入如下：

| 输入 | 作用 |
| --- | --- |
| `t 你好` | 发布文本输入事件。 |
| `asr 你好` | 模拟 STT 已经识别出文本。 |
| `utt 你好` | 模拟用户一句话已经准备好。 |
| `tts 你好` | 发布 TTS 请求事件。 |
| `exec 工具名 参数JSON` | 发布本地执行请求，例如 OpenClaw 工具调用。 |
| `state` | 打印当前 RuntimeContext。 |
| `q` | 退出 Runtime。 |

Runtime 入口用于加载配置、启动 RuntimeApp，并通过事件总线连接后续模块。

## 6. 接入 OpenClaw

OpenClaw 是推荐的 Agent / LLM / 工具处理层，但不是 Sylphos 唯一可用后端。Sylphos 可以把文本输入交给 OpenClaw，再接收 OpenClaw 的原始回复、适合播报的文本、工具结果或执行状态。

**用途**

- 文本理解。
- 任务规划。
- 工具调用或本地控制桥接。
- 向 Sylphos 返回可展示或可播报的结果。

**是否必需**

- 最小 Runtime 文本事件不强制依赖 OpenClaw。
- 需要智能任务处理、工具规划或 OpenClaw 桥接时需要。

**当前状态**

- 仓库已提供 OpenClaw 文本测试、健康检查、bridge 测试和 executor 相关实现。
- OpenClaw 接入方式可能根据你的部署选择 CLI、HTTP、WebSocket 或其他后端。

**相关命令**

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
python scripts/run_openclaw_bridge_test.py --dry-run
```

健康检查命令放在最后的排错附录中。

**相关文件**

- `scripts/test_openclaw_text.py`
- `scripts/run_openclaw_bridge_test.py`
- `scripts/check_openclaw_health.py`
- `sylphos/llm/openclaw_client.py`
- `sylphos/llm/openclaw_http_client.py`
- `sylphos/llm/openclaw_ws_client.py`
- `sylphos/executor/openclaw_bridge.py`
- `sylphos/executor/openclaw_executor.py`
- `sylphos/executor/openclaw_config.py`

**注意事项**

- 首次使用本地执行能力时建议使用 `--dry-run`。
- 不要默认开放全部系统权限。
- OpenClaw 是推荐模块，不是 Sylphos 本体的替代品。

## 7. 接入 SenseVoice / STT

SenseVoice / STT 的作用是：

```text
音频文件 / 音频流 → 文本
```

**用途**

- 将录音文件识别为文本。
- 将语音输入接入 Runtime 下游事件。

**是否必需**

- 文本路径不需要。
- 语音输入路径需要。

**当前状态**

- 仓库已提供 SenseVoice engine、factory、healthcheck 和 Runtime 事件总线模拟入口。
- 当前 healthcheck 入口同时承担最小验证和手动调用用途。

**相关命令**

识别最新录音：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

通过 Runtime 事件总线模式发布结果：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

识别指定 wav：

```bash
python -m sylphos.voice.stt.healthcheck --audio recordings/latest_command.wav --device cpu --language zh
```

**相关文件**

- `docs/asr_sensevoice.md`
- `sylphos/voice/stt/base.py`
- `sylphos/voice/stt/sensevoice.py`
- `sylphos/voice/stt/sensevoice_engine.py`
- `sylphos/voice/stt/factory.py`
- `sylphos/voice/stt/healthcheck.py`
- `sylphos/runtime/stt_handler.py`
- `requirements-asr.txt`

**注意事项**

- SenseVoice 依赖和模型需要单独准备。
- 不建议把 SenseVoice 写死进录音控制器；应通过 STT factory、handler 和事件接入。

## 8. 接入 CosyVoice3 / TTS

CosyVoice3 / TTS 的作用是：

```text
文本 → 语音文件 / 播放输出
```

**用途**

- 将回复文本合成为 wav。
- 在 Runtime 中响应 TTS 请求事件。
- 可选接入 WSL2 FastAPI 服务。

**是否必需**

- 文本路径不需要。
- 需要语音输出时需要。

**当前状态**

- 仓库已提供 TTS engine、factory、healthcheck、Runtime handler、客户端和 WSL2 CosyVoice3 FastAPI 服务模板。
- `requirements-tts.txt` 是 Sylphos TTS 基础依赖，不包含 CosyVoice 本体。

**相关命令**

本地生成 wav：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output outputs/tts/latest_tts.wav --device cpu
```

Runtime 事件总线模拟：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

**相关文件**

Windows / Sylphos 侧客户端与适配器：

- `sylphos/voice/tts/base.py`
- `sylphos/voice/tts/cosyvoice.py`
- `sylphos/voice/tts/cosyvoice_client.py`
- `sylphos/voice/tts/wsl_cosyvoice_client.py`
- `sylphos/voice/tts/tts_client_runtime.py`
- `sylphos/voice/tts/factory.py`
- `sylphos/voice/tts/healthcheck.py`
- `sylphos/runtime/tts_handler.py`

WSL2 / 服务端模板与文档：

- `services/cosyvoice3/cosyvoice_server.py`
- `scripts/start_cosyvoice3_wsl.sh`
- `docs/tts_cosyvoice.md`
- `docs/cosyvoice3_wsl2_windows_deployment.md`

**注意事项**

- `scripts/start_cosyvoice3_wsl.sh` 中的路径是模板示例，需要按你的 WSL 用户名、模型目录和服务目录调整。
- 如果使用 FastAPI 服务，先区分 Windows 侧客户端和 WSL2 侧服务端。
- TTS 推荐通过 `TTSHandler` 响应 `TTSRequested` 事件，不要硬塞进 OpenClaw 客户端或录音控制器。

## 9. 推荐模块说明

| 模块 | 是否必须 | 当前状态 | 作用 | 相关文件 / 命令 |
| --- | --- | --- | --- | --- |
| Sylphos Runtime | 推荐先启动 | 已有交互式入口 | 加载配置、启动 RuntimeApp、发布和处理事件 | `python run_sylphos_runtime.py`、`sylphos/runtime/app.py`、`sylphos/runtime/event_bus.py` |
| AudioHub | 语音输入需要 | 已有实现 | 管理麦克风输入、音频流、采样率、声道和音频块 | `voice/audio/hub.py`、`sylphos/voice/audio/hub.py`、`scripts/runtime_bootstrap.py` |
| WakeWord / openWakeWord | 可选 | 已有适配和运行链路 | 检测唤醒词并触发录音；不是唯一入口 | `voice/wakeword/openwakeword_engine.py`、`sylphos/voice/wakeword/openwakeword_engine.py`、`python scripts/run_wakeword_pipeline.py` |
| VAD | 语音录音推荐 | 已有配置和录音链路接入 | 判断用户是否正在说话，帮助自动结束录音 | `config/voice.py`、`voice/audio/recorder.py`、`sylphos/voice/audio/recorder.py` |
| Recorder / VoiceController | 语音输入需要 | 已有录音控制 | 将一次语音请求录成 wav，例如 `recordings/latest_command.wav` | `sylphos/controller/voice_controller.py`、`voice/audio/recorder.py`、`sylphos/voice/audio/recorder.py` |
| SenseVoice / STT | 语音转文本需要 | 已有 healthcheck、engine、Runtime handler | 将音频文件或音频流转换为文本 | `python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh`、`docs/asr_sensevoice.md` |
| OpenClaw | 智能任务处理推荐 | 已有客户端、healthcheck、bridge、executor | 理解文本、规划任务、桥接工具执行 | `python scripts/test_openclaw_text.py "你好"`、`python scripts/run_openclaw_bridge_test.py --dry-run` |
| Executor | 执行动作时需要 | 已有 base、OpenClaw executor 和 bridge | 执行本地命令、本地 API、桌面控制或插件动作 | `sylphos/executor/base.py`、`sylphos/executor/openclaw_executor.py`、`sylphos/executor/openclaw_bridge.py` |
| CosyVoice3 / TTS | 语音输出需要 | 已有本地适配器、healthcheck、WSL2 服务模板 | 将文本合成为语音文件或播放输出 | `python -m sylphos.voice.tts.healthcheck --text "你好。" --output outputs/tts/latest_tts.wav --device cpu`、`services/cosyvoice3/cosyvoice_server.py` |
| Config | 必需 | 已有默认配置和本地覆盖模板 | 配置模型、设备、服务地址、端口和执行模式 | `sylphos/config/defaults.py`、`sylphos/config/local_config.py.example`、`config/voice.py` |
| Log | 推荐 | OpenClaw bridge 配置中已有日志路径 | 记录运行结果和审计信息，供最后排查 | `logs/sylphos.log`、`logs/audit.jsonl` |

## 10. 配置文件说明

用户通常只需要关注这些配置位置：

| 配置范围 | 文件 | 用途 | 注意事项 |
| --- | --- | --- | --- |
| Runtime / STT / TTS / OpenClaw 默认值 | `sylphos/config/defaults.py` | 默认 provider、服务地址、超时、TTS、OpenClaw 等参数 | 通常不建议直接写入私密信息。 |
| 本地私有配置模板 | `sylphos/config/local_config.py.example` | 提供 OpenClaw token、session、bridge、日志等本地覆盖示例 | 如果创建 `sylphos/config/local_config.py`，不要提交真实 token。 |
| 语音链路配置 | `config/voice.py` | 麦克风、采样率、wakeword、录音、VAD 参数 | 可通过 `config/local_config.py` 覆盖。 |
| 语音本地覆盖 | `config/local_config.py` | 本机麦克风和 wakeword 配置覆盖 | 通常由 `scripts/setup_wakeword.py` 生成或用户自行创建，不应提交 Git。 |
| CosyVoice3 服务模板 | `services/cosyvoice3/cosyvoice_server.py` | WSL2 / 服务端 FastAPI 模板 | 模型路径和环境按本机实际情况配置。 |
| WSL2 启动脚本模板 | `scripts/start_cosyvoice3_wsl.sh` | 启动 WSL2 CosyVoice3 服务 | 示例路径必须改成本机占位路径或真实路径后再用。 |

配置原则：

- 不要把真实 token 写进会提交 Git 的文件。
- 不要在公共文档中写死个人本地路径。
- 本地路径示例应使用占位符，例如 `<your-model-path>`、`<your-service-dir>`。
- 如果 OpenClaw 使用 HTTP 或 WebSocket，确认地址与 `OPENCLAW_HTTP_BASE_URL`、`OPENCLAW_GATEWAY_WS_URL` 等配置一致。
- 如果 TTS 使用服务模式，确认客户端使用的服务地址与实际端口一致。

## 11. 当前限制

1. 当前不是所有模块都已经整合成一个单命令完整语音助手。
2. OpenClaw 接入可能存在 CLI、HTTP、WebSocket、App SDK 等不同方式，需要按实际部署选择。
3. CosyVoice3 可能需要 WSL2 或单独 FastAPI 服务。
4. SenseVoice 模型和依赖需要单独准备。
5. Executor 涉及安全边界，不建议默认开放全部系统权限。
6. WakeWord 是输入触发器，不是 Sylphos 唯一入口；控制台、UI、API 或其他事件也可以作为入口。
7. 推荐组合路径是当前使用建议，不代表系统未来只能按固定顺序运行。

## 12. 最终检查与常见问题

本节是排错附录。只有在按前面的使用路径运行失败后，再集中检查下面项目。

### 12.1 Python 环境

项目当前最低 Python 版本为 Python 3.12。确认运行命令时使用的是同一个 Python 环境。

### 12.2 依赖

按使用范围安装依赖：

```bash
pip install -r requirements.txt
pip install -r requirements-asr.txt
pip install -r requirements-tts.txt
```

`requirements-tts.txt` 不包含 CosyVoice 本体；如果使用 CosyVoice / CosyVoice3，需要按对应项目说明安装源码包和模型依赖。

### 12.3 模型路径

常见模型相关位置：

- openWakeWord 内置模型目录：由 openWakeWord 包提供。
- SenseVoice 模型：由 `sylphos.voice.stt.healthcheck` 加载或初始化。
- CosyVoice3 模型：按 `docs/tts_cosyvoice.md` 和 `docs/cosyvoice3_wsl2_windows_deployment.md` 准备。

不要把大型模型文件提交到 Git。

### 12.4 麦克风

如果唤醒或录音失败，可以列出输入设备：

```bash
python scripts/test_wakeword_pipeline.py --list-devices
```

也可以使用配置向导生成或更新本地音频配置：

```bash
python scripts/setup_wakeword.py
```

### 12.5 STT 是否能返回文本

识别最新录音：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

识别指定 wav：

```bash
python -m sylphos.voice.stt.healthcheck --audio recordings/latest_command.wav --device cpu --language zh
```

### 12.6 OpenClaw 是否启动

检查 OpenClaw 健康状态：

```bash
python scripts/check_openclaw_health.py
```

如果使用 CLI 模式，请确认 `OPENCLAW_CLI_PATH` 或环境中的 `openclaw` 命令可用。如果使用 HTTP / WebSocket 模式，请确认服务地址和端口与配置一致。

### 12.7 OpenClaw 是否能接收文本

文本往返：

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
```

桥接 dry-run：

```bash
python scripts/run_openclaw_bridge_test.py --dry-run
```

### 12.8 TTS 是否能生成音频

本地 TTS 生成 wav：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好。" --output outputs/tts/latest_tts.wav --device cpu
```

如果使用 WSL2 CosyVoice3 FastAPI 服务，请确认服务脚本来自：

```text
services/cosyvoice3/cosyvoice_server.py
```

并根据自己的机器调整 `scripts/start_cosyvoice3_wsl.sh` 中的路径。

### 12.9 TTS 是否能播放声音

先确认是否生成 wav 文件，例如：

```text
outputs/tts/latest_tts.wav
```

如果文件存在但没有声音，优先检查播放器、系统音量和音频输出设备。

### 12.10 日志位置

OpenClaw bridge 配置示例中推荐的日志位置是：

- `logs/sylphos.log`
- `logs/audit.jsonl`

如果日志目录不存在，可以先运行一次 OpenClaw bridge 测试或完整交互。日志用于最后定位问题，不建议每一步都打开日志排查。

### 12.11 当前缺少的一键完整闭环入口

根据当前仓库结构，Sylphos 已有 Runtime、wakeword + recorder、STT healthcheck、OpenClaw 文本测试、OpenClaw bridge 测试、TTS healthcheck 和 CosyVoice3 服务模板。

当前仍缺少一个单命令启动完整语音闭环的入口：

```text
wakeword → recorder → STT → OpenClaw → Executor → TTS
```

建议后续新增专门 launcher 或 Runtime profile，而不是在现有模块中硬编码强链路。
