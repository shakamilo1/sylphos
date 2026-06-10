# Sylphos OpenClaw Bridge

## 1. 为什么 OpenClaw 不直接写进 VoiceController

当前 `VoiceController` 的职责应保持在**语音采集阶段**：唤醒后暂停唤醒词监听、启动录音、录音结束后恢复或重置状态。OpenClaw 则属于文本/任务执行后端，涉及 ASR 后文本输入、任务执行、结构化结果、安全确认、日志审计、语音反馈和 UI 分流。

如果把 OpenClaw 直接写进 `VoiceController`，系统会被固化成“唤醒词 → 录音 → ASR → OpenClaw → TTS”的强链路，后续侧边栏、快捷键、调试命令、远程请求、事件总线、人工确认等入口都会被迫绕过或污染语音控制器。因此本次仅新增 `SylphosOpenClawBridge`，不改动现有 wakeword + recorder 链路。

## 2. 为什么需要 SylphosOpenClawBridge

`SylphosOpenClawBridge` 是 Sylphos 与 OpenClaw 之间的隔离层。它负责：

- 接收来源无关的文本或任务请求；
- 生成 `OpenClawRequest`；
- 调用 OpenClaw CLI、复用 PR #15 HTTP/Gateway client，或保留未来 WebSocket 占位；
- 捕获 stdout、stderr、exit code 和 timeout；
- 将 OpenClaw 输出整理成 executor 层的 `OpenClawBridgeResult`；
- 生成短 `speak_text`，避免把长日志全文交给 TTS；
- 生成 `ui_text`，供侧边栏、终端或未来 UI 展示；
- 写入普通运行日志 `logs/sylphos.log`；
- 写入审计日志 `logs/audit.jsonl`；
- 对高风险请求返回 `needs_confirmation`，避免默认执行。

OpenClaw 在此设计中是 `TOOL_PROVIDER = "openclaw"`，即一个执行器/工具后端，而不是 Sylphos 的核心 Runtime。

## 3. 与 PR #15 的关系

PR #15 已经提供了 `sylphos.llm.openclaw_http_client.OpenClawHTTPClient`、`create_openclaw_client()`、`SpeechReplyAdapter`、`OpenClawSettings`、健康检查脚本和 `runtime.pipeline.handle_transcribed_text()`。本 bridge 不替代 PR #15，而是在它之上增加 source-agnostic request、structured execution result、audit logging、risk confirmation 和 CLI fallback。

当前关系是：

```text
SylphosOpenClawBridge
  ├── dry-run               -> bridge-level simulation, no OpenClaw call
  ├── cli mode              -> subprocess openclaw fallback
  ├── http / gateway mode   -> reuse PR #15 OpenClawHTTPClient
  └── websocket / ws mode   -> reserved future typed streaming protocol
```

因此，已有 Gateway HTTP 能力仍然有效；bridge 只是在 Sylphos 侧提供更适合 UI/TTS/审计/安全分流的执行边界。

PR #15 的最小链路仍然保留：`ASR text -> create_openclaw_client()/OpenClawHTTPClient -> sylphos.llm.types.OpenClawResult(raw_text, spoken_text)`。如果调用方只需要最小 HTTP/Gateway 文本能力，可以继续使用 `runtime.pipeline.handle_transcribed_text()`；如果需要来源无关请求、审计、风险确认、CLI fallback 和结构化执行结果，则使用 `SylphosOpenClawBridge`。

## 4. 当前 CLI 模式只是兜底方案

当前默认配置为：

```python
OPENCLAW_MODE = "cli"  # cli / http / gateway / websocket / ws
OPENCLAW_DRY_RUN = True
OPENCLAW_CLI_PATH = "openclaw"
OPENCLAW_TIMEOUT_SECONDS = 120
```

CLI 模式通过 `subprocess.run()` 调用 OpenClaw，捕获 stdout、stderr、exit code，并处理 timeout、命令不存在和异常。默认 dry-run 不会真正调用 OpenClaw，但仍会完整生成 request/result 和 audit 日志，便于本地验证桥接层数据流。

由于 OpenClaw CLI 的最终参数形式仍需本机实测，命令构造集中在：

```python
def _build_cli_command(self, request: OpenClawRequest) -> list[str]:
    return [self.config.cli_path, request.text]
```

后续如果 OpenClaw CLI 需要 `run --text ...`、stdin、JSON 参数或 workspace 参数，只需要调整这一处。

## 5. Gateway HTTP 与 WebSocket 长期方向

配置中将 HTTP 与未来 WebSocket 地址拆开：

```python
OPENCLAW_HTTP_BASE_URL = "http://127.0.0.1:18789"
OPENCLAW_GATEWAY_WS_URL = "ws://127.0.0.1:18789"
OPENCLAW_AUTH_TOKEN = None
OPENCLAW_CLIENT_ROLE = "operator"
OPENCLAW_SESSION_NAME = "sylphos"
```

`http` / `gateway` 模式会复用 PR #15 的 `OpenClawHTTPClient`，走 OpenAI-compatible HTTP Gateway，并使用 `OPENCLAW_HTTP_BASE_URL`。`websocket` / `ws` 模式当前只返回未实现结果，不强行写死未知协议，未来才会使用 `OPENCLAW_GATEWAY_WS_URL`。早期 `OPENCLAW_GATEWAY_URL` 只作为兼容过渡；如果它是 `ws://`，转换成 `http://` 仅用于兼容旧 bridge 配置，并不代表 WebSocket 已经实现。长期方向是由 typed Gateway WebSocket 承载结构化任务、实时事件、电脑控制结果、确认请求和进度更新。

## 6. workspace 与 `~/.openclaw/` 的区别

- `OPENCLAW_WORKSPACE` 表示 OpenClaw 执行某个用户任务时所在的工作目录，例如一个项目目录或临时操作目录。
- `~/.openclaw/` 通常更适合存放 OpenClaw 自身配置、缓存、会话状态或凭据，不应与当前任务 workspace 混用。

桥接层不会写死个人路径。workspace 默认为 `None`，可通过环境变量或未提交的 `sylphos/config/local_config.py` 覆盖。

## 7. OpenClawBridgeResult 如何分流

项目中有两个不同层级的结果类型：

- `sylphos.llm.types.OpenClawResult`：PR #15 的 HTTP client response，保留最小 `raw_text` / `spoken_text` / `metadata` 能力。
- `sylphos.executor.openclaw_models.OpenClawBridgeResult`：PR #19 的 bridge execution result，用于 UI/TTS/日志/审计/确认/命令结果分流。

`OpenClawBridgeResult` 至少包含以下分流字段：

- `speak_text`：给 TTS 的短文本；
- `ui_text`：给侧边栏、终端或 UI 的展示文本；
- `actions`：结构化动作摘要；
- `files_changed`：文件变更摘要；
- `commands_run`：命令执行摘要；
- `raw_stdout` / `raw_stderr`：原始输出，受 `OPENCLAW_LOG_RAW_OUTPUT` 控制；
- `needs_confirmation` / `confirmation_prompt`：给确认流程使用；
- `status` / `error` / `exit_code`：给错误处理和状态管理使用。

TTS 不直接朗读 raw stdout/stderr。HTTP/Gateway 成功时优先使用 PR #15 `SpeechReplyAdapter` 已生成的 `client_result.spoken_text`。Bridge 自己的 `_make_speak_text()` 主要处理 dry-run、timeout、failed、needs_confirmation 和输出过长兜底。

## 8. 安全确认机制的初步设计

当前 `classify_risk(text)` 先用关键词实现三档风险：

- `low`：查询、打开普通应用、获取状态、读取普通文件等；
- `medium`：创建文件、修改项目文件、运行常见命令，以及无法判断的未知请求；
- `high`：删除/覆盖文件、修改系统配置、未知脚本、联网下载并执行、发送邮件/消息、读取敏感目录、涉及 token/password/secret/ssh key 等。

当前策略：

- high：只有 `context={"confirmed": True}` 这种布尔真值才算确认；字符串 `"false"`、`"0"` 或数字 `1` 都不算确认，未确认时返回 `needs_confirmation`，不执行 OpenClaw；
- medium：允许执行，但审计日志必须记录；
- low：允许直接执行。

后续可以将该函数替换为策略引擎、用户权限模型或事件总线确认流程。

## 9. 下一步如何接 ASR 和 TTS

下一步仍不应在 `VoiceController` 中直接写 OpenClaw 逻辑。建议事件流为：

1. 录音完成后，ASR 模块把 `latest_command.wav` 转成文本；
2. 上层编排器或事件订阅者调用：

   ```python
   result = bridge.submit_text(text, source="voice", context={"audio_file": "latest_command.wav"})
   ```

3. `result.speak_text` 交给 TTS；其中 http/gateway 成功结果优先来自 #15 的 `spoken_text`；
4. `result.ui_text` 交给侧边栏或终端；
5. `result.needs_confirmation` 触发用户确认流程；
6. 审计日志由 OpenClawBridge 统一写入。

TTS 也可以独立用于唤醒后的即时反馈，例如“我在听”，不必等待 OpenClaw 完成。

## 10. 当前限制和待实测项

- OpenClaw CLI 参数仍需根据本机实际版本调整；
- OpenAI-compatible Gateway HTTP 复用 PR #15；typed WebSocket 协议尚未实现；
- CLI 输出解析当前支持纯文本和简单 JSON 对象；HTTP/Gateway 结果复用 #15 `metadata`，复杂事件流需要后续增强；
- 风险分类是基础关键词规则，不是完整安全沙箱；
- 高风险确认只接受 `context["confirmed"] is True`，尚未接 UI/语音确认；
- 电脑控制的细粒度结果需要 OpenClaw 侧提供更稳定的结构化输出字段。

## 11. 测试入口

运行交互测试：

```bash
python scripts/run_openclaw_bridge_test.py --dry-run
```

输入 `q`、`quit` 或 `exit` 退出。脚本会打印 request id、状态、TTS 文本、UI 文本、stdout/stderr 摘要以及日志路径。
