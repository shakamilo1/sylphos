# Sylphos 项目文件组织结构与说明

本文档基于当前仓库实际文件整理，帮助后来维护者快速理解 Sylphos 已有源码、脚本、配置模板、文档，以及它们在“语音输入 → STT → Runtime → Agent/工具执行 → TTS/输出”链路中的关系。

说明：
- 本文只整理项目相关源码、脚本、配置和文档；不展开 `.git/`、`.venv/`、`__pycache__/`、模型权重目录、构建缓存、大型临时音频等。
- 如果某个能力当前主要以文档、示例或模板形式存在，会明确标注“当前状态”。
- OpenClaw 是 Sylphos 推荐的 LLM / Agent / 工具执行层之一，但不是唯一模块；Sylphos 不应被写死为只能调用 OpenClaw。

## 1. 项目整体目录树

```text
sylphos/
├─ sylphos/                         # Sylphos Python 包主体
│  ├─ runtime/                       # 事件驱动 Runtime、事件、上下文、编排器
│  ├─ config/                        # 默认配置、配置加载器、本地配置模板
│  ├─ executor/                      # 执行器抽象与 OpenClaw bridge/executor
│  ├─ llm/                           # Agent/LLM 客户端抽象与 OpenClaw 客户端
│  ├─ voice/
│  │  ├─ audio/                      # Runtime 内部音频 Hub / Recorder 适配
│  │  ├─ stt/                        # STT 抽象、SenseVoice、dummy、健康检查
│  │  ├─ tts/                        # TTS 抽象、CosyVoice/TTSClient、健康检查
│  │  └─ wakeword/                   # Runtime 内部 openWakeWord 适配
│  ├─ controller/                    # VoiceController 语音控制流程
│  ├─ frontend/                      # 控制台反馈入口
│  └─ mcp/                           # MCP 相关占位/核心定义
├─ voice/                            # 较早期或独立语音链路模块
│  ├─ audio/                         # AudioHub、Recorder、EventBridge
│  ├─ wakeword/                      # WakeWord 抽象、控制器、openWakeWord 引擎
│  └─ VAD/                           # Silero VAD 手动验证脚本
├─ services/
│  └─ cosyvoice3/                    # CosyVoice3 FastAPI 服务模板
├─ scripts/                          # 启动、健康检查、桥接、wakeword 辅助脚本
├─ tests/                            # pytest 单元/集成测试
├─ docs/                             # ASR、TTS、OpenClaw、部署与本文档
├─ config/                           # 项目根级语音配置/本地配置覆盖
├─ run_sylphos_runtime.py            # Runtime 交互式控制台入口
├─ detect_from_microphone.py         # 麦克风检测/唤醒示例入口
├─ test_openwakeword_win11.py        # Windows openWakeWord 手动验证脚本
├─ requirements*.txt                 # 运行、ASR、TTS 依赖清单
├─ environment.yml                   # Conda 环境配置
├─ pyproject.toml                    # 项目与 pytest 配置
├─ readme.me / readme.txt            # 项目说明文件
└─ .github/workflows/ci.yml          # CI 配置
```

## 2. Sylphos 本体相关文件

### `run_sylphos_runtime.py`

当前状态：已实现

作用：
- 提供交互式 Runtime 控制台入口。
- 加载配置、初始化 `RuntimeApp`、启动 Runtime，并允许手动发布 wakeword、ASR、TTS、OpenClaw 执行、UI、状态跳转等事件。

主要被谁调用：
- 由维护者或本地用户直接运行。
- 依赖 `sylphos.config.loader`、`sylphos.runtime.app`、`sylphos.runtime.events`。

维护注意：
- 新增 Runtime 事件后，可在此补充手动触发命令，便于调试。
- 不要在入口中写死私密路径、token 或单一 Agent 提供方。

### `sylphos/runtime/app.py`

当前状态：已实现

作用：
- Runtime 组装入口，负责从配置创建 EventBus、RuntimeContext、RuntimeRegistry、RuntimeOrchestrator、Recorder、WakeWord、STT、TTS、OpenClaw executor、ConsoleFeedback 等组件。
- 将配置字段映射为 wakeword、录音、STT、TTS、OpenClaw 后端参数。

主要被谁调用：
- `run_sylphos_runtime.py`。
- Runtime 相关测试。

维护注意：
- 这是当前最接近“统一入口”的地方，新增模块时优先保持 provider 可插拔。
- OpenClaw、SenseVoice、CosyVoice 都应通过配置启用，不应强制成为唯一选择。

### `sylphos/runtime/events.py`

当前状态：已实现

作用：
- 定义 Runtime 内部事件类型，包括输入、录音、ASR、用户意图、工具执行、TTS、UI、状态控制、错误等事件。

主要被谁调用：
- `EventBus`、`RuntimeOrchestrator`、`STTHandler`、`TTSHandler`、Recorder/WakeWord 适配器、控制台入口和测试。

维护注意：
- 新事件应保持命名清晰，并考虑向后兼容已有事件字段。
- 事件字段中不要保存敏感 token 或大块音频二进制。

### `sylphos/runtime/event_bus.py`

当前状态：已实现

作用：
- 提供同步、进程内 EventBus。
- 支持按事件类型订阅/取消订阅/发布，并在 handler 抛错时发布 `ErrorOccurred`。

主要被谁调用：
- RuntimeApp、编排器、STT/TTS handler、音频和唤醒适配器。

维护注意：
- 当前是同步实现；如果后续引入异步或跨进程事件，需要明确兼容层。
- handler 中的长耗时任务可能阻塞事件流。

### `sylphos/runtime/orchestrator.py`

当前状态：已实现

作用：
- Runtime 编排器，订阅关键事件并推进“唤醒 → 录音 → ASR → 用户文本 → 路由/工具执行 → TTS/UI”的最小流程。
- 包含简单路由器 `SimpleRouter`。

主要被谁调用：
- `RuntimeApp` 初始化并注册。
- 依赖 `RuntimeContext`、`RuntimeRegistry`、`EventBus` 和事件定义。

维护注意：
- 它是教学/最小链路的核心编排点；长期应避免把所有业务规则堆在单个编排器里。
- 新增分支流程时要考虑事件驱动和可插拔目标。

### `sylphos/runtime/context.py`

当前状态：已实现

作用：
- 保存 Runtime 当前状态、会话信息、最后一次用户文本、ASR 结果、TTS 结果等上下文数据。

主要被谁调用：
- `RuntimeApp`、`RuntimeOrchestrator`、控制台状态查看命令、测试。

维护注意：
- 上下文适合保存轻量状态，不适合长期保存敏感信息或大型二进制。

### `sylphos/runtime/state.py`

当前状态：已实现

作用：
- 定义 Runtime 状态常量/枚举，用于描述待机、监听、录音、识别、执行、播报等状态。

主要被谁调用：
- `RuntimeContext` 和编排器相关流程。

维护注意：
- 新增状态时需同步更新编排器、测试和文档中的状态流说明。

### `sylphos/runtime/registry.py`

当前状态：已实现

作用：
- Runtime 服务注册表，用于保存 recorder、wakeword、stt、tts、executor、frontend 等服务实例。

主要被谁调用：
- `RuntimeApp` 负责注册，`RuntimeOrchestrator` 和 handler 按需读取。

维护注意：
- 服务 key 应保持稳定，避免隐式字符串漂移导致运行期找不到组件。

### `sylphos/runtime/stt_handler.py`

当前状态：已实现

作用：
- 监听 ASR/STT 请求事件，调用配置的 STT 引擎，并发布识别成功或失败事件。

主要被谁调用：
- `RuntimeApp` 装配后订阅 EventBus。
- 依赖 `sylphos.voice.stt` 中的 STT 引擎。

维护注意：
- SenseVoice 模型加载可能依赖外部环境，handler 应继续保持错误事件可观测。

### `sylphos/runtime/tts_handler.py`

当前状态：已实现

作用：
- 监听 TTS 请求事件，调用配置的 TTS 引擎，并发布合成成功或失败事件。

主要被谁调用：
- `RuntimeApp` 装配后订阅 EventBus。
- 依赖 `sylphos.voice.tts` 中的 TTS provider。

维护注意：
- 播放音频、写文件和远程 TTS 调用都可能阻塞；后续可考虑异步化或任务队列。

### `sylphos/runtime/message_bus.py`

当前状态：预留接口

作用：
- 提供消息总线相关结构，和 `EventBus` 同属 Runtime 通信层概念。

主要被谁调用：
- 当前主链路主要使用 `event_bus.py`。

维护注意：
- 如果后续保留两个 bus 概念，需要明确 EventBus 与 MessageBus 的边界，避免重复。

### `sylphos/runtime/pipeline.py`

当前状态：预留接口

作用：
- 管线抽象相关文件，用于表达更结构化的处理流程。

主要被谁调用：
- 当前主入口仍以 `RuntimeOrchestrator` + EventBus 为主。

维护注意：
- 若未来引入可配置 pipeline，应与事件模型和 Registry 对齐。

### `sylphos/config/defaults.py`

当前状态：已实现

作用：
- 提供 Sylphos 默认配置，包括音频、唤醒词、录音、STT、TTS、OpenClaw、日志等默认值。

主要被谁调用：
- `sylphos.config.loader.load_config()`。

维护注意：
- 默认值不应包含真实密钥、token、个人绝对路径。
- 新增配置项后，应同步更新模板、相关文档和测试。

### `sylphos/config/loader.py`

当前状态：已实现

作用：
- 按层加载配置：默认配置、根目录 `local_config.py`、`sylphos/config/local_config.py`、项目根 `config/local_config.py`、环境变量覆盖。

主要被谁调用：
- `run_sylphos_runtime.py`、`RuntimeApp` 和配置测试。

维护注意：
- 不要在 loader 中打印或暴露敏感配置值。
- 修改加载优先级时需同步 `tests/test_config_loader.py`。

### `sylphos/config/settings.py`

当前状态：已实现

作用：
- 定义 OpenClaw 等结构化 settings，并从配置/环境中生成运行所需设置。

主要被谁调用：
- `sylphos.executor.openclaw_bridge`、`sylphos.llm.openclaw_http_client` 等。

维护注意：
- token、session key 等应支持环境变量或本地配置，但文档只能使用占位符。

### `sylphos/executor/base.py`

当前状态：已实现

作用：
- 定义执行器抽象接口，供 OpenClaw 或未来本地工具执行器实现。

主要被谁调用：
- Runtime executor 注册与测试。

维护注意：
- 保持抽象接口与 OpenClaw 解耦，方便未来接入其他 Agent/工具执行层。

### `sylphos/executor/openclaw_bridge.py`

当前状态：已实现

作用：
- Sylphos 与 OpenClaw 之间的 source-agnostic bridge。
- 将用户文本封装为 OpenClaw 请求，进行风险分类、敏感信息脱敏、日志记录，并调用 OpenClaw client 或本地 CLI/API/WebSocket 后端。

主要被谁调用：
- `OpenClawExecutor`、桥接测试、`scripts/run_openclaw_bridge_test.py`。

维护注意：
- 继续保持敏感字段脱敏。
- OpenClaw 是推荐模块，不是唯一模块；bridge 不应污染通用 executor 抽象。

### `sylphos/executor/openclaw_executor.py`

当前状态：已实现

作用：
- 提供 Runtime 可注册的 OpenClaw executor，包括 dummy、CLI、API、WebSocket 等后端封装。

主要被谁调用：
- `RuntimeApp` 根据配置选择 executor provider。
- Runtime OpenClaw executor 测试。

维护注意：
- dry-run 和真实执行路径要保持清晰，避免调试时误执行高风险操作。

### `sylphos/executor/openclaw_config.py`

当前状态：已实现

作用：
- 定义 OpenClaw bridge 配置、默认 URL、日志路径、执行模式等。

主要被谁调用：
- `RuntimeApp`、`openclaw_bridge.py`、OpenClaw 测试和脚本。

维护注意：
- 本地地址和 token 应通过本地配置或环境变量覆盖，不要提交真实私密值。

### `sylphos/executor/openclaw_models.py`

当前状态：已实现

作用：
- 定义 OpenClaw 请求与返回结果的数据模型。

主要被谁调用：
- `openclaw_bridge.py`、OpenClaw executor 和测试。

维护注意：
- 修改字段时需考虑日志兼容和测试断言。

### `sylphos/llm/base.py`

当前状态：已实现

作用：
- 定义 Agent/LLM 客户端基础接口。

主要被谁调用：
- OpenClaw client、OpenClaw bridge。

维护注意：
- 应保持 provider-agnostic，不要加入 OpenClaw 专属字段。

### `sylphos/llm/types.py`

当前状态：已实现

作用：
- 定义 LLM/Agent 返回结果类型，例如 raw_text、spoken_text、metadata 等。

主要被谁调用：
- OpenClaw HTTP/WebSocket client 和 bridge。

维护注意：
- 字段应兼容语音播报链路，不要只面向文本 UI。

### `sylphos/llm/openclaw_client.py`

当前状态：已实现

作用：
- OpenClaw client 工厂、异常类型和语音回复适配器。

主要被谁调用：
- `openclaw_bridge.py`、HTTP/WebSocket client。

维护注意：
- 适配器负责将 Agent 输出变成适合 TTS 的短回复，应避免输出过长或包含敏感信息。

### `sylphos/llm/openclaw_http_client.py`

当前状态：已实现

作用：
- 使用 OpenAI-compatible `POST /v1/chat/completions` 调用 OpenClaw Gateway。

主要被谁调用：
- `create_openclaw_client()`、OpenClaw bridge、HTTP client 测试。

维护注意：
- Header 中可能包含 token，日志只能记录是否存在，不应记录 token 原文。

### `sylphos/llm/openclaw_ws_client.py`

当前状态：已实现

作用：
- OpenClaw WebSocket 客户端实现。

主要被谁调用：
- OpenClaw client 工厂和 WebSocket executor 配置。

维护注意：
- WebSocket 协议字段变化时，需要同步文档和测试。

### `sylphos/llm/openclaw_health.py`

当前状态：已实现

作用：
- OpenClaw 健康检查逻辑，用于验证服务可达性、认证和基础响应。

主要被谁调用：
- `scripts/check_openclaw_health.py`、健康检查测试。

维护注意：
- 健康检查应区分连接失败、认证失败、接口不存在等问题。

### `sylphos/frontend/console_feedback.py`

当前状态：已实现

作用：
- 控制台反馈前端，订阅 Runtime 事件并输出用户可见提示。

主要被谁调用：
- `RuntimeApp`。

维护注意：
- 当前是最小交互前端；不要把业务逻辑写入 console feedback。

### `sylphos/controller/voice_controller.py`

当前状态：已实现

作用：
- 语音控制器，负责把 wakeword、录音和 STT/TTS 链路组织成更高层的控制流程。

主要被谁调用：
- 当前 Runtime 主链路更多由 `RuntimeOrchestrator` 管理；该文件可作为语音控制抽象补充。

维护注意：
- 需要避免与 RuntimeOrchestrator 职责重复，后续可统一边界。

### `sylphos/mcp/core.py`

当前状态：预留接口

作用：
- MCP 相关核心结构，当前不是主语音链路必需模块。

主要被谁调用：
- 目前未出现在最小 Runtime 主链路中。

维护注意：
- 后续若接入 MCP 工具，应明确其与 executor/plugins/local tools 的关系。

## 3. 语音输入链路相关文件

### `sylphos/voice/audio/hub.py`

当前状态：已实现

作用：
- Runtime 内部 AudioHub 适配器，用于连接音频输入事件和 Runtime EventBus。

主要被谁调用：
- `RuntimeApp`。

维护注意：
- 与根目录 `voice/audio/hub.py` 存在功能相近文件，后续需要统一归属。

### `sylphos/voice/audio/recorder.py`

当前状态：已实现

作用：
- Runtime 使用的录音服务，支持保存 wav、VAD 参数、latest 文件名、录音目录等配置。

主要被谁调用：
- `RuntimeApp`、Runtime recorder 测试。

维护注意：
- 临时录音文件默认应写入输出目录，不应提交到仓库。
- VAD 参数变化时应同步默认配置和文档。

### `sylphos/voice/wakeword/openwakeword_engine.py`

当前状态：已实现

作用：
- Runtime 内部 openWakeWord 引擎适配器，读取 wakeword 配置并向 EventBus 发布唤醒事件。

主要被谁调用：
- `RuntimeApp`、wakeword 配置测试。

维护注意：
- 模型文件路径应通过配置指定，不应把模型权重纳入源码结构。

### `voice/audio/base.py`

当前状态：已实现

作用：
- 较早期或独立语音链路中的音频抽象基类。

主要被谁调用：
- 根目录 `voice/audio/*` 模块。

维护注意：
- 与 `sylphos/voice/audio/*` 有重叠，后续建议明确是否迁移进包内。

### `voice/audio/hub.py`

当前状态：已实现

作用：
- 独立 AudioHub 实现，负责组织麦克风输入、wakeword、录音事件等。

主要被谁调用：
- `scripts/run_wakeword_pipeline.py`、`scripts/test_wakeword_pipeline.py` 或手动验证链路。

维护注意：
- 与 Runtime 内部 AudioHub 适配器职责相近，文档和代码中应说明差异。

### `voice/audio/recorder.py`

当前状态：已实现

作用：
- 独立录音器实现，用于麦克风录音和保存音频文件。

主要被谁调用：
- 独立 wakeword pipeline、麦克风检测脚本。

维护注意：
- 注意输出目录、采样率、设备索引和 Windows/WSL2 环境差异。

### `voice/audio/event_bridge.py`

当前状态：已实现

作用：
- 将独立语音链路事件桥接到其他事件处理逻辑。

主要被谁调用：
- 独立 wakeword/audio pipeline。

维护注意：
- 如果 Runtime EventBus 成为统一事件层，需评估是否复用或迁移该 bridge。

### `voice/wakeword/base.py`

当前状态：已实现

作用：
- WakeWord 引擎抽象基类。

主要被谁调用：
- 根目录 wakeword controller 和 openWakeWord engine。

维护注意：
- 保持和包内 wakeword adapter 的接口边界清晰。

### `voice/wakeword/openwakeword_engine.py`

当前状态：已实现

作用：
- 独立 openWakeWord 引擎实现，用于检测唤醒词。

主要被谁调用：
- 独立 wakeword pipeline 和手动测试脚本。

维护注意：
- 模型路径、采样率和阈值应通过配置调整，不要写死到源码。

### `voice/wakeword/controller.py`

当前状态：已实现

作用：
- 独立 wakeword 控制器，用于管理唤醒监听的启动、暂停、恢复等。

主要被谁调用：
- 独立 wakeword pipeline。

维护注意：
- 与 Runtime 中的 `PauseWakeWordRequested` / `ResumeWakeWordRequested` 事件语义保持一致。

### `voice/VAD/test_silero_vad.py`

当前状态：手动验证脚本

作用：
- 用于验证 Silero VAD 能否在当前环境运行。

主要被谁调用：
- 维护者手动运行。

维护注意：
- 依赖 torch/silero 等环境，不能视为稳定单元测试。

### `detect_from_microphone.py`

当前状态：示例/手动验证脚本

作用：
- 从麦克风输入检测音频或唤醒相关能力。

主要被谁调用：
- 本地调试者手动运行。

维护注意：
- 依赖本机麦克风设备和系统音频权限，CI 中通常不可直接运行。

## 4. SenseVoice / STT 相关文件

STT 在 Sylphos 中的位置：

```text
音频文件 / 音频流 → STT → 文本结果 → Sylphos Runtime / OpenClaw
```

### `sylphos/voice/stt/base.py`

当前状态：已实现

作用：
- 定义 STT 引擎抽象和 ASR 结果结构。

主要被谁调用：
- SenseVoice、DummySTT、Runtime STT handler。

维护注意：
- 保持接口简洁，避免绑定单一 STT 提供方。

### `sylphos/voice/stt/sensevoice.py`

当前状态：已实现

作用：
- 封装 FunASR / SenseVoice 模型加载和音频文件转写。
- 清理 SenseVoice 输出中的语言/情绪等标签，并返回结构化 ASR 结果。

主要被谁调用：
- `SenseVoiceRuntimeAdapter`、STT factory、健康检查或手动验证。

维护注意：
- 依赖 `requirements-asr.txt` 中的 ASR 依赖和模型下载环境。
- 不能把模型权重或缓存目录写入文档主结构。

### `sylphos/voice/stt/sensevoice_engine.py`

当前状态：已实现

作用：
- Runtime adapter 层，将 SenseVoice 引擎适配为 Runtime STT provider。

主要被谁调用：
- `sylphos.voice.stt.__init__`、STT factory、`RuntimeApp`。

维护注意：
- 修改返回结构时要同步 `STTHandler` 和测试。

### `sylphos/voice/stt/factory.py`

当前状态：已实现

作用：
- 根据 provider 配置创建 STT 引擎，例如 dummy 或 SenseVoice。

主要被谁调用：
- `RuntimeApp`。

维护注意：
- 新增 STT provider 时应从这里接入，避免散落条件判断。

### `sylphos/voice/stt/dummy_stt.py`

当前状态：已实现

作用：
- 提供不依赖模型的 dummy STT，用于测试和无模型环境。

主要被谁调用：
- Runtime 默认/测试配置。

维护注意：
- 适合 CI，不代表真实 ASR 效果。

### `sylphos/voice/stt/healthcheck.py`

当前状态：已实现

作用：
- STT 健康检查入口，用于检查依赖、模型加载和转写流程。

主要被谁调用：
- 维护者通过 `python -m sylphos.voice.stt.healthcheck` 手动运行。

维护注意：
- 需要区分依赖缺失、模型不可下载、音频文件不存在等错误。

### `docs/asr_sensevoice.md`

当前状态：文档说明

作用：
- 说明 SenseVoice / ASR 的安装、配置和使用方式。

主要被谁调用：
- 需要部署或调试 STT 的维护者阅读。

维护注意：
- 如果 `requirements-asr.txt` 或配置项变化，需要同步更新。

### `requirements-asr.txt`

当前状态：配置/依赖清单

作用：
- 记录 ASR/SenseVoice 相关 Python 依赖。

主要被谁调用：
- 部署者或健康检查文档。

维护注意：
- 避免把平台特定大包或私有源地址写死；必要时在文档中说明平台差异。

## 5. OpenClaw 接入相关文件

OpenClaw 是 Sylphos 的推荐 LLM / Agent / 工具执行层之一，但 Sylphos 不应该被写死为只能调用 OpenClaw。OpenClaw 是推荐模块，不是唯一模块；`sylphos/llm/base.py` 和 `sylphos/executor/base.py` 应继续保持 provider-agnostic。

### `sylphos/executor/openclaw_bridge.py`

当前状态：已实现

作用：
- 将 Sylphos 文本请求提交到 OpenClaw，并返回结构化结果。
- 负责风险分类、脱敏、日志和 dry-run/真实执行路径。

主要被谁调用：
- `OpenClawExecutor`、桥接测试、OpenClaw 调试脚本。

维护注意：
- 不要泄露 token、password、api key、authorization 等字段。
- 高风险操作分类规则变化时应补测试。

### `sylphos/executor/openclaw_executor.py`

当前状态：已实现

作用：
- 将 OpenClaw bridge 包装为 Runtime 工具执行器。

主要被谁调用：
- `RuntimeApp` 和 Runtime 工具执行事件链路。

维护注意：
- 真实执行和 dry-run 的默认值必须安全。

### `sylphos/llm/openclaw_http_client.py`

当前状态：已实现

作用：
- 通过 HTTP 调用 OpenClaw Gateway 的 chat completions API。

主要被谁调用：
- OpenClaw client 工厂、bridge、测试。

维护注意：
- 接口路径或协议变化时，同步 `docs/openclaw_integration.md`。

### `sylphos/llm/openclaw_ws_client.py`

当前状态：已实现

作用：
- 通过 WebSocket 接入 OpenClaw。

主要被谁调用：
- OpenClaw client 工厂和 WebSocket executor 后端。

维护注意：
- 需要和 OpenClaw 端事件协议保持一致。

### `sylphos/llm/openclaw_health.py`

当前状态：已实现

作用：
- OpenClaw 健康检查实现。

主要被谁调用：
- `scripts/check_openclaw_health.py` 和测试。

维护注意：
- 健康检查输出可以包含服务地址和状态，但不能输出认证 token。

### `scripts/check_openclaw_health.py`

当前状态：已实现

作用：
- 命令行健康检查脚本，用于验证 OpenClaw 服务是否可达。

推荐使用场景：
- 接入 OpenClaw 前确认网关、token、model、session 配置是否正确。

注意事项：
- 需要 OpenClaw 服务运行。
- token 应来自本地配置或环境变量，不要写入脚本。

### `scripts/test_openclaw_text.py`

当前状态：手动验证脚本

用途：
- 发送一段文本到 OpenClaw，用于验证文本请求链路。

推荐使用场景：
- 在 Runtime 接入前单独检查 OpenClaw 文本能力。

注意事项：
- 依赖 OpenClaw 服务和本地配置。

### `scripts/run_openclaw_bridge_test.py`

当前状态：手动验证脚本

用途：
- 运行 OpenClaw bridge 测试/演示流程。

推荐使用场景：
- 调试 Sylphos 到 OpenClaw 的桥接层。

注意事项：
- 注意 dry-run 配置，避免误执行真实工具动作。

### `docs/openclaw_integration.md`

当前状态：文档说明

作用：
- 说明 OpenClaw 与 Sylphos 的集成方式、启动和配置要点。

适合读者：
- 需要把 Sylphos 接到 OpenClaw Gateway / Agent 的维护者。

维护注意：
- 如果 HTTP/WebSocket/App SDK/API 协议变化，需要同步更新。

### `docs/openclaw_bridge.md`

当前状态：文档说明

作用：
- 说明 Sylphos OpenClaw bridge 的设计、运行、日志和安全边界。

适合读者：
- 维护 bridge、executor、安全策略和日志的人。

维护注意：
- 与 `openclaw_bridge.py` 的风险分类、日志字段保持一致。

## 6. CosyVoice3 / TTS 相关文件

TTS 在 Sylphos 中的位置：

```text
文本回复 → TTS 服务 → 音频文件 / 音频流 → 播放输出
```

### `services/cosyvoice3/cosyvoice_server.py`

当前状态：模板

作用：
- CosyVoice3 FastAPI 服务模板，提供 TTS 服务端接口和健康检查接口。

主要被谁调用：
- WSL2/Linux 服务部署者手动启动。
- Windows 或 Sylphos TTS client 通过 HTTP 调用。

维护注意：
- 需要实际 CosyVoice3 依赖和模型环境。
- 服务地址、端口、模型路径应通过配置或启动参数控制。

### `sylphos/voice/tts/base.py`

当前状态：已实现

作用：
- 定义 TTS provider 抽象和合成结果结构。

主要被谁调用：
- DummyTTS、CosyVoice、TTSClientRuntimeAdapter、TTSHandler。

维护注意：
- 保持和具体 TTS 服务解耦。

### `sylphos/voice/tts/tts_client_runtime.py`

当前状态：已实现

作用：
- 将外部 TTSClient 路径适配为 Runtime TTS provider。

主要被谁调用：
- `RuntimeApp` 根据 `TTS_PROVIDER` 创建 TTS engine。

维护注意：
- 应明确 base/tts_client/cosyvoice provider 的差异，避免配置含义混乱。

### `sylphos/voice/tts/cosyvoice_client.py`

当前状态：已实现

作用：
- CosyVoice HTTP 客户端，用于调用外部 TTS 服务并获取音频。

主要被谁调用：
- TTS provider、测试或 Windows 客户端调用路径。

维护注意：
- 超时、输出路径和音频播放行为应可配置。

### `sylphos/voice/tts/wsl_cosyvoice_client.py`

当前状态：已实现

作用：
- 面向 WSL2/Windows 跨环境部署的 CosyVoice 客户端。

主要被谁调用：
- `tests/test_wsl_cosyvoice_client.py`、部署文档中的客户端调用说明。

维护注意：
- Windows host 与 WSL2 IP、端口、防火墙设置可能变化，应在文档中说明。

### `sylphos/voice/tts/cosyvoice.py`

当前状态：已实现

作用：
- 直接源码安装 CosyVoice 后的本地 TTS adapter。

主要被谁调用：
- TTS factory 或健康检查在 provider 为 `cosyvoice` 时使用。

维护注意：
- 依赖 CosyVoice 本体源码安装，不应默认要求所有开发者安装。

### `sylphos/voice/tts/factory.py`

当前状态：已实现

作用：
- 根据 provider 创建 TTS 引擎。

主要被谁调用：
- `RuntimeApp`、TTS 健康检查。

维护注意：
- 新增 TTS provider 时优先接入 factory。

### `sylphos/voice/tts/dummy_tts.py`

当前状态：已实现

作用：
- 不依赖模型的 dummy TTS，用于测试或无 TTS 环境。

主要被谁调用：
- Runtime 默认配置、测试。

维护注意：
- 不能代表真实音频合成能力。

### `sylphos/voice/tts/healthcheck.py`

当前状态：已实现

作用：
- CosyVoice TTS 健康检查入口，可检查 Python 版本、依赖、模型加载、合成输出和 Runtime EventBus 流程。

主要被谁调用：
- 维护者通过 `python -m sylphos.voice.tts.healthcheck` 手动运行。

维护注意：
- 健康检查已实现，但真实运行依赖 Python、torch、modelscope、cosyvoice、模型路径和设备。

### `docs/tts_cosyvoice.md`

当前状态：文档说明

作用：
- 说明 CosyVoice / TTS 的安装、配置、健康检查和 Runtime 接入。

适合读者：
- 需要在 Sylphos 中启用 TTS 的维护者。

维护注意：
- 如果 provider 名称、健康检查参数或依赖清单变化，需要同步更新。

### `docs/cosyvoice3_wsl2_windows_deployment.md`

当前状态：文档说明

作用：
- 说明 CosyVoice3 在 WSL2 服务端与 Windows 客户端之间的部署和调用方式。

适合读者：
- 需要在 WSL2 中部署 TTS 服务，并从 Windows/Sylphos 调用的人。

维护注意：
- 如果 FastAPI 服务端口、健康检查路径或客户端调用方式变化，需要同步更新。

### `requirements-tts.txt`

当前状态：配置/依赖清单

作用：
- 记录 TTS/CosyVoice 相关 Python 依赖。

主要被谁调用：
- 部署者、健康检查文档、CI/本地环境准备。

维护注意：
- CosyVoice 本体可能需要源码安装，文档中应继续说明依赖边界。

## 7. 配置文件与本地配置模板

### `sylphos/config/defaults.py`

当前状态：已实现

作用：
- 默认配置集中位置，覆盖音频设备、采样率、wakeword、录音、VAD、STT、TTS、OpenClaw、日志等。

维护注意：
- 默认配置必须安全、可提交、无私密信息。

### `sylphos/config/local_config.py.example`

当前状态：模板

作用：
- 包内本地配置模板，供用户复制为 `sylphos/config/local_config.py` 后按本机环境覆盖。

维护注意：
- 模板只能使用占位符，例如 `<OPENCLAW_TOKEN>`、`<MODEL_PATH>`。
- 真实 local config 不应提交敏感信息。

### `config/voice.py`

当前状态：已实现

作用：
- 项目根级语音配置，包含麦克风、采样率、wakeword、VAD 等语音链路参数。

主要被谁调用：
- 独立 `voice/` 链路和相关脚本。

维护注意：
- 与 `sylphos/config/defaults.py` 有部分重叠，后续建议统一配置来源。

### `config/local_config.py`

当前状态：本地配置

作用：
- 项目根级本地配置覆盖文件，`sylphos.config.loader` 会读取它。

维护注意：
- 不要在文档或提交中泄露真实 token、密码、私有模型路径或个人绝对路径。
- 如需示例，应新增 `.example` 模板而不是记录真实值。

### `requirements.txt`

当前状态：配置/依赖清单

作用：
- Sylphos 基础运行依赖。

维护注意：
- ASR/TTS 大型依赖尽量保留在 `requirements-asr.txt` / `requirements-tts.txt`，降低基础安装成本。

### `environment.yml`

当前状态：配置/依赖清单

作用：
- Conda 环境配置。

维护注意：
- 如果 Python 版本或核心依赖升级，需要同步文档和 CI。

### `pyproject.toml`

当前状态：已实现

作用：
- 项目元信息和 pytest 配置。

维护注意：
- 测试路径、依赖声明和包名变化时需同步。

### `.github/workflows/ci.yml`

当前状态：已实现

作用：
- GitHub Actions CI 配置。

维护注意：
- CI 不应依赖本地麦克风、模型权重或私有服务；相关测试应 mock 或跳过。

## 8. 脚本文件说明

### `scripts/runtime_bootstrap.py`

用途：
- Runtime 启动辅助脚本，用于初始化或演示 Runtime 运行所需环境。

推荐使用场景：
- 本地调试 Runtime 前检查基础链路。

注意事项：
- 具体行为应与 `run_sylphos_runtime.py` 保持一致，避免出现两个不同入口语义。

### `scripts/check_openclaw_health.py`

用途：
- 检查 OpenClaw 服务健康状态。

推荐使用场景：
- 配置 OpenClaw 地址、token、model 后先运行该脚本验证服务。

注意事项：
- 需要 OpenClaw 服务运行；不要在命令行或日志中暴露真实 token。

### `scripts/test_openclaw_text.py`

用途：
- 向 OpenClaw 发送文本并检查返回。

推荐使用场景：
- 调试 Sylphos → OpenClaw 文本路径。

注意事项：
- 依赖 OpenClaw Gateway/API 可达。

### `scripts/run_openclaw_bridge_test.py`

用途：
- 运行 OpenClaw bridge 调试流程。

推荐使用场景：
- 验证 bridge 风险分类、请求封装、日志输出和返回结构。

注意事项：
- 注意 dry-run 设置，避免真实执行危险操作。

### `scripts/setup_wakeword.py`

用途：
- wakeword 环境或模型设置辅助脚本。

推荐使用场景：
- 首次配置 openWakeWord 前运行或参考。

注意事项：
- 可能涉及模型下载或本地路径，模型文件不应提交。

### `scripts/run_wakeword_pipeline.py`

用途：
- 运行独立 wakeword/audio pipeline。

推荐使用场景：
- 在完整 Runtime 之前单独调试麦克风、唤醒词和录音链路。

注意事项：
- 依赖本机音频设备、openWakeWord 模型和系统权限。

### `scripts/test_wakeword_pipeline.py`

用途：
- 手动测试 wakeword pipeline。

推荐使用场景：
- 调整阈值、模型路径、麦克风设备后验证唤醒效果。

注意事项：
- 更接近手动验证脚本，不应等同于 CI 稳定单元测试。

### `scripts/start_cosyvoice3_wsl.sh`

用途：
- 在 WSL2/Linux 环境启动 CosyVoice3 服务。

推荐使用场景：
- 根据 `docs/cosyvoice3_wsl2_windows_deployment.md` 部署 TTS 服务时使用。

注意事项：
- 依赖 WSL2/Linux、Python 环境、CosyVoice3 依赖、模型路径和端口配置。

### `detect_from_microphone.py`

用途：
- 麦克风输入检测或唤醒链路示例。

推荐使用场景：
- 本机音频设备调试。

注意事项：
- 依赖本地麦克风，CI 不适合运行。

### `test_openwakeword_win11.py`

用途：
- Windows 11 环境下 openWakeWord 手动验证。

推荐使用场景：
- Windows 本机调试唤醒词模型和麦克风输入。

注意事项：
- 依赖 Windows 音频设备和 openWakeWord 环境。

### `download.py`

用途：
- 下载辅助脚本。

推荐使用场景：
- 准备模型或资源时参考。

注意事项：
- 下载目标不应被当成项目源码提交；如需凭证应使用环境变量或本地配置。

## 9. 文档文件说明

### `docs/asr_sensevoice.md`

适合读者：
- 需要部署或维护 SenseVoice / ASR 链路的开发者。

主要内容：
- ASR 依赖安装、模型加载、健康检查、Runtime 接入和常见问题。

维护注意：
- 与 `sylphos/voice/stt/*`、`requirements-asr.txt`、默认配置保持一致。

### `docs/tts_cosyvoice.md`

适合读者：
- 需要启用 CosyVoice / TTS 的维护者。

主要内容：
- 依赖安装、CosyVoice 本体说明、provider 配置、健康检查和 Runtime 事件链路。

维护注意：
- 与 `sylphos/voice/tts/*`、`requirements-tts.txt`、健康检查脚本保持一致。

### `docs/cosyvoice3_wsl2_windows_deployment.md`

适合读者：
- 需要在 WSL2 中部署 CosyVoice3 服务，并从 Windows/Sylphos 调用的用户。

主要内容：
- WSL2 部署、FastAPI 服务、健康检查、Windows 客户端访问和网络注意事项。

维护注意：
- 与 `services/cosyvoice3/cosyvoice_server.py`、`scripts/start_cosyvoice3_wsl.sh`、WSL 客户端保持一致。

### `docs/openclaw_integration.md`

适合读者：
- 需要把 Sylphos 接入 OpenClaw Gateway / Agent 的维护者。

主要内容：
- OpenClaw 服务地址、API/WebSocket 接入、配置项、启动说明和语音到 Agent 的流程。

维护注意：
- 与 `sylphos/llm/openclaw_*` 和 `sylphos/executor/openclaw_*` 保持一致。

### `docs/openclaw_bridge.md`

适合读者：
- 维护 Sylphos ↔ OpenClaw bridge、安全策略和执行日志的人。

主要内容：
- Bridge 设计、风险分类、dry-run、日志、审计和调试方式。

维护注意：
- 与 `sylphos/executor/openclaw_bridge.py` 保持一致。

### `docs/project_file_structure.md`

适合读者：
- 新加入的维护者、需要快速理解仓库结构的人。

主要内容：
- 当前项目目录树、源码/脚本/配置/文档/测试说明、模块调用关系和缺口建议。

维护注意：
- 每次新增关键目录、入口、provider 或部署方式后应更新本文档。

### `readme.me` / `readme.txt`

适合读者：
- 首次打开仓库的用户或维护者。

主要内容：
- 项目概览、基础说明或历史说明。

维护注意：
- 当前存在两个 readme 文件，建议后续统一命名为标准 `README.md`，并保留必要历史内容。

## 10. 测试文件说明

### `tests/test_config_loader.py`

当前状态：单元测试

说明：
- 验证配置加载顺序、覆盖逻辑和环境变量处理。

运行前需要：
- 基础 Python 测试依赖。

### `tests/test_runtime_recorder_service.py`

当前状态：单元/集成测试

说明：
- 验证 Runtime recorder 服务和事件/文件输出相关行为。

运行前需要：
- 可能需要音频相关依赖；测试应避免依赖真实麦克风。

### `tests/test_runtime_wakeword_config.py`

当前状态：单元测试

说明：
- 验证 Runtime wakeword 配置映射。

运行前需要：
- 不应依赖真实模型权重。

### `tests/test_runtime_tts_provider.py`

当前状态：单元测试

说明：
- 验证 Runtime TTS provider 选择和配置。

运行前需要：
- 默认应可使用 dummy/mock 路径，不要求真实 CosyVoice。

### `tests/test_runtime_openclaw_executor.py`

当前状态：单元/集成测试

说明：
- 验证 Runtime OpenClaw executor 行为。

运行前需要：
- 应优先使用 dummy/dry-run/mock，避免依赖真实 OpenClaw。

### `tests/test_openclaw_bridge.py`

当前状态：单元测试

说明：
- 验证 OpenClaw bridge 请求、风险分类、脱敏和结果结构。

运行前需要：
- 基础 Python 测试依赖。

### `tests/test_openclaw_http_client.py`

当前状态：单元测试

说明：
- 验证 OpenClaw HTTP client 请求构造、响应解析和异常处理。

运行前需要：
- 一般通过 mock，不应要求真实 OpenClaw 服务。

### `tests/test_openclaw_health.py`

当前状态：单元测试

说明：
- 验证 OpenClaw 健康检查逻辑。

运行前需要：
- 一般通过 mock，不应要求真实 OpenClaw 服务。

### `tests/test_cosyvoice_server.py`

当前状态：单元/集成测试

说明：
- 验证 CosyVoice3 FastAPI 服务模板行为。

运行前需要：
- 可能需要 FastAPI/TestClient 相关依赖；不应强制要求真实模型。

### `tests/test_wsl_cosyvoice_client.py`

当前状态：单元测试

说明：
- 验证 WSL CosyVoice client 的 URL、请求或响应处理。

运行前需要：
- 一般不应要求真实 WSL 服务。

### `tests/conftest.py`

当前状态：测试基础设施

说明：
- pytest 公共 fixture 和路径设置。

运行前需要：
- pytest。

### 手动验证脚本

当前状态：手动验证

文件：
- `voice/VAD/test_silero_vad.py`
- `test_openwakeword_win11.py`
- `scripts/test_wakeword_pipeline.py`
- `scripts/test_openclaw_text.py`

说明：
- 这些脚本依赖本机音频设备、模型、外部服务或系统环境，不能简单视为稳定 CI 单元测试。

## 11. 模块之间的调用关系

当前最小教学路径如下：

```text
用户语音
  ↓
AudioHub / Recorder
  ↓
WakeWord / VAD / VoiceController
  ↓
SenseVoice / STT
  ↓
Sylphos Runtime
  ↓
OpenClaw / LLM / Agent
  ↓
Executor / Plugins / Local Tools
  ↓
TTSClient / CosyVoice3
  ↓
语音播放 / 日志 / 前端输出
```

更贴近当前代码的事件流可以理解为：

```text
WakeWordDetected
  ↓
RuntimeOrchestrator
  ↓
RecordingRequested → RecorderService → RecordingCompleted
  ↓
ASRRequested → STTHandler → ASRCompleted / ASRFailed
  ↓
UserUtteranceReady / TextInputReceived
  ↓
ToolExecutionRequested → OpenClawExecutor / SylphosOpenClawBridge
  ↓
TTSRequested → TTSHandler → TTSCompleted / TTSFailed
  ↓
ConsoleFeedback / 日志 / 音频输出
```

说明：
- 这只是当前最小教学路径，不代表 Sylphos 未来只能固定按这条链路运行。
- Sylphos 的长期目标是事件驱动、模块可插拔，允许从任意模块切入和切出。
- OpenClaw、SenseVoice、CosyVoice3 都应作为可替换 provider，而不是不可替换的硬编码依赖。

## 12. 当前缺口与后续建议

### 已有代码的模块

- Runtime / EventBus / 事件定义 / 编排器：`sylphos/runtime/*`。
- 配置加载：`sylphos/config/*` 与项目根 `config/*`。
- OpenClaw bridge、executor、HTTP/WebSocket client、健康检查：`sylphos/executor/openclaw_*`、`sylphos/llm/openclaw_*`。
- STT 抽象、SenseVoice、dummy、健康检查：`sylphos/voice/stt/*`。
- TTS 抽象、CosyVoice/TTSClient/dummy、健康检查：`sylphos/voice/tts/*`。
- 语音输入、wakeword、recorder：`sylphos/voice/audio/*`、`sylphos/voice/wakeword/*`、根目录 `voice/*`。

### 只有文档或主要依赖文档说明的模块

- OpenClaw 部署/集成细节主要在 `docs/openclaw_integration.md` 和 `docs/openclaw_bridge.md`。
- CosyVoice3 WSL2/Windows 部署主要在 `docs/cosyvoice3_wsl2_windows_deployment.md`。
- SenseVoice 安装和使用主要在 `docs/asr_sensevoice.md`。

### 只有模板或半成品的模块

- `services/cosyvoice3/cosyvoice_server.py` 是 FastAPI 服务模板，真实可用性取决于 CosyVoice3 环境和模型。
- `sylphos/mcp/core.py` 更像预留能力，不在当前最小语音主链路中。
- `sylphos/runtime/message_bus.py`、`sylphos/runtime/pipeline.py` 与当前 EventBus/Orchestrator 主链路存在潜在重叠，边界待明确。

### 还缺统一入口的地方

- 语音输入链路目前同时存在包内 `sylphos/voice/audio/*` 和根目录 `voice/audio/*`，需要后续明确统一入口。
- wakeword 也存在包内和根目录两套实现/适配，建议明确哪些用于 Runtime，哪些用于独立实验。
- TTS 有本地 CosyVoice、HTTP client、WSL client、TTSClient runtime adapter 多条路径，建议在 README 或配置文档中给出推荐默认路径。

### 文件命名或目录位置建议整理

- `readme.me` 与 `readme.txt` 建议后续合并或迁移为标准 `README.md`。
- 根目录 `config/` 与 `sylphos/config/` 的职责有重叠，建议补充配置优先级说明或逐步收敛。
- 根目录 `voice/` 与 `sylphos/voice/` 存在相似能力，建议后续迁移或标注“legacy/experimental”。
- `scripts/test_*.py` 命名容易与 pytest 测试混淆；如果是手动验证脚本，可考虑改名为 `check_*.py` 或 `demo_*.py`。

### 文档和实际代码可能不一致的风险

- OpenClaw HTTP/WebSocket 协议如果随 OpenClaw Gateway 变化，`docs/openclaw_integration.md`、`docs/openclaw_bridge.md` 和 `sylphos/llm/openclaw_*` 需要同步。
- CosyVoice3 服务模板与实际 CosyVoice3 安装方式可能因上游变化而失配，需要定期用健康检查验证。
- SenseVoice/FunASR 依赖和模型下载方式可能变化，`requirements-asr.txt` 与 `docs/asr_sensevoice.md` 需要同步维护。

### 后续建议

1. 新增标准 `README.md`，用一页说明推荐启动路径：Runtime、OpenClaw、STT、TTS、wakeword。
2. 为 `config/local_config.py` 提供脱敏的 `.example`，并在文档中说明不要提交真实密钥或个人路径。
3. 明确 `voice/` 是否为 legacy/experimental；如果是，文档和目录名应标注清楚。
4. 为 Runtime 增加一个统一健康检查入口，串联配置、OpenClaw、STT、TTS、音频设备可用性。
5. 将手动验证脚本与 pytest 测试命名区分，降低维护者误解。
6. 为 OpenClaw 以外的 LLM/Agent provider 预留示例实现，验证 Sylphos 不被写死为 OpenClaw-only。
