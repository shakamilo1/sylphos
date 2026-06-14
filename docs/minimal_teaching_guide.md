# Sylphos 最小教学文档：从本体到推荐模块

这是一份给普通用户和第一次接触 Sylphos 的人的“最小教学文档”。它不是完整开发手册，也不是排错大全。你应该先理解系统如何组成、按最短路径跑通一次交互，最后再集中检查环境和问题。

## 1. Sylphos 是什么

Sylphos 是一个**本地自然语言交互与计算机控制系统**。它不是单纯的语音助手，也不是一条写死的流水线程序。

更容易理解的说法是：Sylphos 本体负责把“输入、理解、执行、输出”这些环节组织起来，让不同模块可以被注册、替换和调度。它的核心设计是：

- **模块化**：语音识别、LLM、工具执行、语音合成都可以单独替换。
- **事件驱动**：模块之间尽量通过事件传递结果，而不是互相写死调用。
- **可替换**：当前推荐 SenseVoice 做 STT、OpenClaw 做 LLM / Agent、CosyVoice3 做 TTS，但未来可以换成其他实现。
- **可扩展**：后续模块可以从任意环节切入、修改、中断、追加或跳转，而不是只能沿着一条固定路线运行。

为了教学，当前最小闭环可以先理解为：

```text
唤醒 / 输入 → 语音识别 STT → LLM / OpenClaw → 工具执行 / 本地控制 → 语音合成 TTS → 输出
```

但这只是“最小教学路径”，不代表 Sylphos 未来只能按这个固定顺序运行。

### Sylphos 本体负责什么

普通用户可以把 Sylphos 本体理解成“总控与连接层”，大致包含这些职责：

1. **配置管理**：读取默认配置、本地覆盖配置、服务地址、模型参数、设备选择等。
2. **事件总线 / Runtime**：把“唤醒了”“录音完成了”“识别完成了”“需要播报”等消息传给对应模块。
3. **模块注册与调度**：让 STT、TTS、OpenClaw、执行器等模块以统一方式接入。
4. **任务执行入口**：提供命令行 Runtime，让用户可以用文本或事件模拟一次交互。
5. **日志记录**：保存关键调用和执行结果，方便最后统一排查。
6. **安全边界**：尤其是本地执行模块，不建议默认开放全部系统权限。
7. **本地工具或插件接口**：把“打开浏览器”“调用本地 API”“执行桌面操作”等能力交给专门模块。
8. **前端或交互入口**：目前仓库中有控制台反馈和交互式 Runtime，后续可以接 Web UI、桌面端等。
9. **语音模块统一接入层**：让麦克风、唤醒词、录音、STT、TTS 不必相互写死。

## 2. 最小运行闭环

第一次学习时，不建议一上来就同时启动所有模型和服务。更推荐按下面的最小闭环理解：

1. 用户通过文本命令或唤醒词进入 Sylphos。
2. 如果是语音输入，AudioHub 读取麦克风音频流。
3. WakeWord 检测到唤醒词后，VoiceController / Recorder 开始录制本次请求。
4. VAD 判断用户是否还在说话，帮助录音自动结束。
5. STT / SenseVoice 把 wav 音频转成文本。
6. Sylphos 把文本交给 OpenClaw。
7. OpenClaw 理解意图、规划任务、调用工具，或返回文本结果。
8. Executor 在安全边界内执行本地命令、本地 API、桌面控制或插件动作。
9. TTS / CosyVoice3 把需要播报的文本转成语音。
10. Sylphos 输出文本、声音或后续事件。

如果你只是第一次体验，最短路径可以先走“文本 → OpenClaw → 文本结果”，然后再接入 STT 和 TTS。

## 3. 推荐模块总览

### 3.1 AudioHub / 音频输入层

AudioHub 负责统一管理麦克风输入、音频流、采样率、声道和音频块。它把连续音频分发给唤醒词、录音器等订阅者。

仓库中与 AudioHub 相关的实现主要在：

- `voice/audio/hub.py`
- `sylphos/voice/audio/hub.py`
- `scripts/runtime_bootstrap.py`

当前推荐把 AudioHub 当作“音频入口”，不要让每个模块自己重复打开麦克风。

### 3.2 WakeWord / 唤醒词模块

WakeWord 负责检测唤醒词，例如 openWakeWord。仓库中已有 openWakeWord 适配和唤醒链路脚本。

需要注意：唤醒词只是一个**输入触发器**，不应该被写死为 Sylphos 的唯一入口。Sylphos 也可以从控制台文本、UI、API 或其他事件进入。

相关文件包括：

- `voice/wakeword/openwakeword_engine.py`
- `sylphos/voice/wakeword/openwakeword_engine.py`
- `scripts/run_wakeword_pipeline.py`
- `scripts/setup_wakeword.py`

### 3.3 VAD / 语音活动检测

VAD 用于判断用户是否正在说话，减少无效录音，并帮助一次语音请求在用户说完后自动结束。

当前 VAD 参数在 `config/voice.py` 中，例如 `VAD_ENABLED`、`VAD_THRESHOLD`、`VAD_END_SILENCE_MS` 等。普通用户不需要一开始就调这些参数，先用默认值即可。

### 3.4 VoiceController / 录音控制

VoiceController / Recorder 负责把一次用户语音请求录成音频文件，例如临时 wav 文件。当前默认录音目录和最新录音文件名在 `config/voice.py` 中配置：

- `RECORDINGS_DIR = "recordings"`
- `LATEST_RECORD_FILENAME = "latest_command.wav"`

也就是说，最小语音链路中常见的识别输入是：

```text
recordings/latest_command.wav
```

### 3.5 STT / SenseVoice

STT 负责把语音转成文本。Sylphos 当前推荐使用 SenseVoice 作为正式 ASR / STT 模块。

推荐最小入口是健康检查模块：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

如果要通过 Runtime 事件总线模拟接入，可以使用：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

STT 的详细安装和模型初始化说明见 `docs/asr_sensevoice.md`。本教学文档只保留最短入口，不展开训练、模型原理或复杂调参。

### 3.6 LLM / OpenClaw

OpenClaw 在 Sylphos 中负责理解文本、规划任务、调用工具、控制电脑，或把结果返回给 Sylphos。

Sylphos 与 OpenClaw 的关系可以这样理解：

1. Sylphos 收到文本输入，例如来自控制台、STT 或 UI。
2. Sylphos 把文本交给 OpenClaw。
3. OpenClaw 返回原始结果、适合播报的文本、工具调用结果或执行状态。
4. Sylphos 再决定是否语音播报、记录日志、展示到前端，或者触发后续动作。

仓库中与 OpenClaw 相关的最小入口包括：

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
```

以及桥接测试：

```bash
python scripts/run_openclaw_bridge_test.py --dry-run
```

如果需要检查 OpenClaw 服务健康状态，可以最后再运行：

```bash
python scripts/check_openclaw_health.py
```

### 3.7 Executor / 本地执行模块

Executor 负责实际执行本地命令、本地 API、桌面控制或插件动作。OpenClaw 可以规划任务，但真正触碰本地系统的动作应该由执行模块在 Sylphos 的安全边界内完成。

普通用户要特别注意：执行模块涉及系统权限，不建议无脑开放所有命令、所有文件、所有桌面控制权限。第一次运行时，建议优先使用 dry-run 或受限模式，确认 OpenClaw 输出符合预期后再逐步开放能力。

相关文件包括：

- `sylphos/executor/base.py`
- `sylphos/executor/openclaw_executor.py`
- `sylphos/executor/openclaw_bridge.py`
- `sylphos/executor/openclaw_config.py`

### 3.8 TTS / CosyVoice3

TTS 负责把回复文本变成语音。Sylphos 当前推荐 CosyVoice / CosyVoice3 方向，并提供了本地 TTS 适配器、健康检查入口、TTSClient 和 WSL CosyVoice3 FastAPI 服务模板。

最小本地健康检查入口：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output outputs/tts/latest_tts.wav --device cpu
```

Runtime 事件总线模拟入口：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

如果使用 WSL2 中的 CosyVoice3 FastAPI 服务，仓库模板在：

```text
services/cosyvoice3/cosyvoice_server.py
```

仓库也提供了启动脚本模板：

```text
scripts/start_cosyvoice3_wsl.sh
```

需要注意：`scripts/start_cosyvoice3_wsl.sh` 中包含示例路径，普通用户应按自己的 WSL 用户名、模型路径和服务目录调整。

### 3.9 Log / 日志模块

日志用于最后排查，不应该让普通用户每一步都查日志。

OpenClaw 桥接配置示例中包含日志路径：

- `logs/sylphos.log`
- `logs/audit.jsonl`

如果交互失败，建议先跑完一次最短路径，再到最后的“最终检查与常见问题”统一查看日志。

### 3.10 Config / 配置模块

配置文件用于选择模型路径、音频设备、服务地址、端口、执行模式等。

当前仓库中常见配置位置包括：

- `sylphos/config/defaults.py`：Runtime、STT、TTS、OpenClaw 等默认配置。
- `sylphos/config/local_config.py.example`：本地私有配置模板，不要提交真实 token。
- `config/voice.py`：wakeword、麦克风、录音、VAD 等语音链路配置。
- `config/local_config.py`：可选本地覆盖文件，通常由 `scripts/setup_wakeword.py` 生成或用户自己创建，不应提交到 Git。

普通用户第一次运行时，先尽量使用默认配置；只有遇到设备、模型路径、服务地址不匹配时，再修改本地覆盖配置。

## 4. 普通用户应该先准备什么

第一次运行只需要准备最少的东西：

1. Python 3.12 环境。
2. 项目依赖：主依赖、ASR 依赖、TTS 依赖按需要安装。
3. 如果要用语音输入：一个可用麦克风。
4. 如果要用 SenseVoice：准备 STT 依赖和模型缓存。
5. 如果要用 OpenClaw：确保 OpenClaw 本体或服务已经按你的运行方式准备好。
6. 如果要用 CosyVoice3：准备 CosyVoice / CosyVoice3 依赖、模型和可选 FastAPI 服务。

不要在这里反复检查每个细节。先按下一节走最短路径，失败后再到最后统一排查。

## 5. 第一次运行的最短路径

建议第一次按这个顺序：

1. 先启动 Sylphos Runtime，用控制台文本模拟输入。
2. 再接 OpenClaw，确认“文本 → OpenClaw → 文本结果”能跑通。
3. 再接 STT，让录音文件能转成文本。
4. 最后接 TTS，让结果能播报出来。
5. 如果你需要完整语音体验，再启动 wakeword + recorder 音频链路。

最小命令可以先从 Runtime 开始：

```bash
python run_sylphos_runtime.py
```

进入提示符后，可以输入：

```text
t 你好，介绍一下 Sylphos
```

这一步的意义是：先确认 Sylphos 本体的事件入口和控制台交互方式，而不是一开始就被麦克风、模型和音频服务卡住。

## 6. 启动 Sylphos 本体

Sylphos 本体的最小入口是：

```bash
python run_sylphos_runtime.py
```

这个入口会加载配置、启动 RuntimeApp，并提供一个交互式控制台。你可以用它模拟不同事件，例如：

- `t 文本`：发布文本输入。
- `asr 文本`：模拟语音识别完成。
- `utt 文本`：模拟用户一句话已经准备好。
- `tts 文本`：请求 TTS 播报。
- `exec 工具名 参数JSON`：请求本地执行模块。
- `state`：查看当前 Runtime 状态。
- `q`：退出。

普通用户第一次只需要记住：用 `t 你的文本` 可以先走文本输入路径。

## 7. 接入语音识别

语音识别的最小接入方式是：先让录音链路生成 `recordings/latest_command.wav`，再用 SenseVoice 识别它。

如果你只想跑唤醒和录音链路，可以使用：

```bash
python scripts/run_wakeword_pipeline.py
```

这条链路会通过 `scripts/runtime_bootstrap.py` 组装 AudioHub、openWakeWord、Recorder、VAD 和 RuntimeOrchestrator。

录音文件准备好后，使用 STT 最小入口：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

如果要让 STT 结果通过 Runtime 事件总线发布，使用：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --runtime --json
```

当前建议：STT 作为可替换模块接入，不要把 SenseVoice 写死进 VoiceController。未来替换 Whisper 或其他 STT 时，应只扩展 STT factory 和 engine。

## 8. 接入 OpenClaw

OpenClaw 可以先独立做文本往返测试：

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
```

如果你要测试 Sylphos 到 OpenClaw 的桥接层，可以使用 dry-run：

```bash
python scripts/run_openclaw_bridge_test.py --dry-run
```

dry-run 适合第一次使用，因为它可以先观察 Sylphos 准备提交给 OpenClaw 的内容和返回结构，不急着执行真实本地动作。

在完整链路中，OpenClaw 不应该直接替代 Sylphos 本体。更推荐的关系是：Sylphos 负责接入、事件、日志、安全边界和后续动作；OpenClaw 负责理解文本、规划任务和产生可执行建议或结果。

## 9. 接入语音合成

TTS 可以先独立合成一句话：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好，我是 Sylphos。" --output outputs/tts/latest_tts.wav --device cpu
```

如果要模拟 Runtime 事件总线中的 TTS 请求，可以使用：

```bash
python -m sylphos.voice.tts.healthcheck --text "你好。" --runtime --json
```

如果你使用 CosyVoice3 FastAPI 服务，优先参考：

- `docs/tts_cosyvoice.md`
- `docs/cosyvoice3_wsl2_windows_deployment.md`
- `services/cosyvoice3/cosyvoice_server.py`
- `scripts/start_cosyvoice3_wsl.sh`

当前建议：TTS 由 `TTSHandler` 响应 `TTSRequested` 事件，不要把 TTS 硬塞进录音控制器或 OpenClaw 客户端里。

## 10. 一次完整交互是怎么流动的

一次完整语音交互可以这样理解：

1. AudioHub 打开麦克风并分发音频流。
2. WakeWord 检测到唤醒词，发布唤醒事件。
3. RuntimeOrchestrator 暂停或切换唤醒监听，安排录音。
4. Recorder / VoiceController 录制本次请求。
5. VAD 判断用户说完后，录音结束，生成 wav 文件。
6. STTHandler 接收录音完成事件，调用 SenseVoice。
7. SenseVoice 返回文本，并发布 ASR 完成事件。
8. Sylphos 把文本交给 OpenClaw 或执行器。
9. OpenClaw 返回结果、工具调用建议或执行状态。
10. Executor 在安全边界内执行本地动作。
11. Sylphos 记录日志、更新状态，并按需要请求 TTS。
12. TTSHandler 调用 CosyVoice / CosyVoice3，把文本合成为语音。
13. 用户听到或看到结果。

再次强调：这是最小教学路径，不是未来架构限制。Sylphos 后续应该允许模块从任意环节切入、修改、中断、追加或跳转。

## 11. 后续可以替换哪些模块

Sylphos 的推荐模块不是永久绑定。后续可以替换或扩展：

- AudioHub：换不同音频后端或远程音频输入。
- WakeWord：从 openWakeWord 换成其他唤醒词引擎，或完全不用唤醒词。
- VAD：调整策略或替换成其他 VAD 实现。
- STT：从 SenseVoice 换成 Whisper、云端 STT 或其他本地模型。
- LLM / Agent：OpenClaw 可以作为推荐 Agent，也可以预留其他 LLM / Agent 接口。
- Executor：按权限拆分本地命令、桌面控制、浏览器控制、本地 API、插件系统。
- TTS：从 CosyVoice3 换成其他 TTS 引擎，或接远程 TTS 服务。
- Frontend：从控制台扩展到 Web UI、桌面 UI、移动端或其他交互入口。
- Log：从本地文件扩展到结构化日志、审计日志或可视化面板。

如果某个模块当前还只是半成品，建议先保留接口和文档说明，不要为了凑完整链路而把逻辑写死。

## 12. 最终检查与常见问题

只有当你按最短路径运行失败，才建议集中检查下面这些项目。

### 12.1 Python 环境是否正确

项目说明中当前最低 Python 版本为 Python 3.12。请确认你运行命令时使用的是同一个 Python 环境。

### 12.2 依赖是否安装

按使用范围安装依赖：

```bash
pip install -r requirements.txt
pip install -r requirements-asr.txt
pip install -r requirements-tts.txt
```

`requirements-tts.txt` 不包含 CosyVoice 本体；如果使用 CosyVoice / CosyVoice3，需要按对应项目说明安装其源码包和模型依赖。

### 12.3 模型路径是否存在

常见模型相关位置：

- openWakeWord 内置模型目录：由 openWakeWord 包提供。
- SenseVoice 模型：由 `sylphos.voice.stt.healthcheck` 加载或初始化。
- CosyVoice3 模型：按 `docs/tts_cosyvoice.md` 和 `docs/cosyvoice3_wsl2_windows_deployment.md` 准备。

不要把大型模型文件提交到 Git。

### 12.4 麦克风是否可用

如果唤醒或录音失败，可以最后再列出输入设备：

```bash
python scripts/test_wakeword_pipeline.py --list-devices
```

也可以使用配置向导生成或更新本地音频配置：

```bash
python scripts/setup_wakeword.py
```

### 12.5 STT 服务是否能返回文本

识别最新录音：

```bash
python -m sylphos.voice.stt.healthcheck --latest --device cpu --language zh
```

如果没有最新录音，可以指定 wav 文件：

```bash
python -m sylphos.voice.stt.healthcheck --audio recordings/latest_command.wav --device cpu --language zh
```

### 12.6 OpenClaw 是否启动

检查 OpenClaw 健康状态：

```bash
python scripts/check_openclaw_health.py
```

如果使用 CLI 模式，请确认 `OPENCLAW_CLI_PATH` 或环境中的 `openclaw` 命令可用。如果使用 HTTP / WebSocket 模式，请确认服务地址和端口与配置一致。

### 12.7 OpenClaw 是否能接收文本输入

可以先跑文本往返：

```bash
python scripts/test_openclaw_text.py "你好，介绍一下 Sylphos"
```

或者使用桥接 dry-run：

```bash
python scripts/run_openclaw_bridge_test.py --dry-run
```

### 12.8 TTS 服务是否启动

本地 TTS 健康检查：

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

如果文件存在但没有声音，优先检查播放器、系统音量、音频输出设备，而不是马上修改 Sylphos 代码。

### 12.10 日志文件在哪里看

OpenClaw 桥接配置示例中推荐的日志位置是：

- `logs/sylphos.log`
- `logs/audit.jsonl`

如果日志目录不存在，可以先运行一次 OpenClaw 桥接测试或完整交互。日志用于最后定位问题，不建议每走一步都打开日志排查。

### 12.11 目前可能缺少或仍需后续完善的入口

根据当前仓库结构，Sylphos 已经有 Runtime、wakeword + recorder、STT healthcheck、OpenClaw 文本测试、OpenClaw bridge 测试、TTS healthcheck 和 CosyVoice3 服务模板。

但“一个命令启动完整语音闭环：wakeword → recorder → STT → OpenClaw → Executor → TTS”的总入口目前仍建议作为后续完善项。现阶段更稳妥的学习方式是按本文顺序分别跑通各模块，再逐步接成完整事件链路。
