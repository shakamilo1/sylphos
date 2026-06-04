# Sylphos OpenClaw 集成说明

## 定位：Agent / Executor，而不是普通聊天模型

Sylphos 将 OpenClaw 视为本地任务执行 Agent、工具路由器和电脑控制执行层。语音链路中的 SenseVoice 只负责把用户语音转成文本；OpenClaw 负责理解任务、路由工具、执行或协调本地操作；CosyVoice 只负责朗读适合语音输出的文本。

因此 Runtime 层只依赖简单边界：

```python
ask(text: str) -> OpenClawResult
```

Runtime 不直接处理 OpenClaw token、HTTP headers、session key 或 Gateway 细节。

## 当前 HTTP 方案

第一阶段使用 OpenClaw Gateway 的 OpenAI-compatible HTTP API：

```text
POST {OPENCLAW_BASE_URL}/v1/chat/completions
```

Sylphos 发送 system + user messages，使用 `OPENCLAW_MODEL` 指定模型，并通过 headers 传递 session 与 message channel。`OPENCLAW_TOKEN` 为空时不会发送 `Authorization` header。

返回值统一为 `OpenClawResult`：

- `raw_text`：OpenClaw 原始完整文本，用于日志、前端或调试。
- `spoken_text`：清洗 Markdown 并限制长度后的文本，适合交给 CosyVoice。
- `metadata`：保留 usage、finish_reason、run_id/raw_response 等调试信息。

## 未来 SDK / WebSocket 方案

`OpenClawWSClient` 已预留第二阶段结构。未来目标包括：

- typed WebSocket API 连接；
- agent run 启动与状态监听；
- streaming events；
- tool event 展示；
- partial/final text callback；
- cancel(run_id)；
- approval / confirmation；
- 语音唤醒词或 stop command 触发打断；
- 多 agent 路由。

当前不引入 Node.js SDK 作为 Python 依赖。如果将来需要 `@openclaw/sdk`，建议采用独立 bridge：

```text
Sylphos Python -> local Node bridge process -> @openclaw/sdk -> OpenClaw Gateway
```

## 快速配置 OpenClaw 接口

Sylphos 的 OpenClaw 接口通过环境变量配置；如果环境变量不存在，则使用 `sylphos/config/settings.py` 中的安全默认值。`sylphos/config/local_config.py.example` 只是给本地配置做参考模板，当前运行时不会自动导入真实 `local_config.py`。

最小配置示例：

```bash
export OPENCLAW_BASE_URL="http://127.0.0.1:18789"
export OPENCLAW_MODEL="openclaw"
export OPENCLAW_SESSION_KEY="sylphos-main"
export OPENCLAW_MESSAGE_CHANNEL="sylphos-voice"
# 如果 Gateway 开启了 token，再设置 OPENCLAW_TOKEN；不要把真实 token 写入仓库。
export OPENCLAW_TOKEN="<your-openclaw-token>"
```

如需手动验证接口，可以先启动本机 OpenClaw Gateway，然后运行：

```bash
python scripts/test_openclaw_text.py "打开 Sylphos 项目"
```

脚本会打印用户文本、OpenClaw 原始回复，以及 Sylphos 准备交给 CosyVoice 的朗读文本。

## 配置项

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `OPENCLAW_BASE_URL` | `http://127.0.0.1:18789` | OpenClaw Gateway 地址，默认只连接本机。 |
| `OPENCLAW_TOKEN` | 空 | Gateway token；为空时不发送 Authorization。 |
| `OPENCLAW_MODEL` | `openclaw` | OpenAI-compatible API model 字段。 |
| `OPENCLAW_SESSION_KEY` | `sylphos-main` | 默认会话 key；每次 `ask(..., session_key=...)` 可覆盖。 |
| `OPENCLAW_MESSAGE_CHANNEL` | `sylphos-voice` | OpenClaw 消息 channel。 |
| `OPENCLAW_TIMEOUT_SECONDS` | `120` | HTTP 请求超时。 |
| `OPENCLAW_MAX_SPOKEN_CHARS` | `300` | 朗读文本最大长度。 |

可参考 `sylphos/config/local_config.py.example`，但不要提交包含真实密钥的 `local_config.py` 或 `.env`。

## 安全注意事项

OpenClaw Gateway token 等同于高权限本地操作入口：

1. 不要把 token 写入源码或提交到 Git。
2. 不要在日志中打印 token；Sylphos 只记录 token 是否存在。
3. 默认只连接 `127.0.0.1`，不要把 Gateway 直接暴露到公网。
4. 如确需远程访问，只建议使用 Tailscale、私有网络，或带强鉴权的反向代理方案。
5. 危险操作未来必须支持 approval / confirmation；当前版本只预留接口。

## SenseVoice 与 CosyVoice 的边界

本集成不安装、配置或改动 SenseVoice 与 CosyVoice。

典型调用链：

```text
WakeWord -> VAD -> SenseVoice -> OpenClaw -> CosyVoice
```

边界如下：

- SenseVoice 输出文本，交给 `runtime.pipeline.handle_transcribed_text()`。
- OpenClaw client 返回 `OpenClawResult`。
- Runtime 或事件编排层只把 `OpenClawResult.spoken_text` 交给 TTS。
- `OpenClawResult.raw_text` 保留给日志、UI 或调试，不直接朗读。

## 未来 TODO

- streaming；
- cancel；
- approval；
- multi-agent；
- spoken_text/full_text 双输出；
- tool event 语音提示；
- WebSocket event 到 Runtime EventBus 的映射；
- 语音打断时取消 OpenClaw run 并停止 TTS。
