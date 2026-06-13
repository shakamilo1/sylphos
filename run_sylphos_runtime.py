from __future__ import annotations

import json
import logging

from sylphos.config.loader import load_config
from sylphos.runtime.app import RuntimeApp, configure_logging
from sylphos.runtime.events import (
    ASRCompleted, CancelCurrentTaskRequested, PauseWakeWordRequested, ResumeWakeWordRequested,
    RuntimeJumpRequested, StepRetryRequested, StepSkipped, TTSRequested, TextInputReceived,
    ToolExecutionRequested, UIMessageRequested, UserUtteranceReady, WakeWordDetected,
)

HELP = """
命令:
  q                         退出 Runtime
  w                         模拟 WakeWordDetected
  r                         恢复唤醒监听
  p                         暂停唤醒监听
  c                         取消当前任务
  t 文本                    发布 TextInputReceived
  asr 文本                  发布 ASRCompleted
  utt 文本                  发布 UserUtteranceReady
  tts 文本                  发布 TTSRequested
  exec 工具名 参数JSON       发布 ToolExecutionRequested，例如 exec openclaw {"command":"打开浏览器"}
  ui 文本                   发布 UIMessageRequested
  state                     打印 RuntimeContext
  jump 状态名               发布 RuntimeJumpRequested
  retry 步骤名              发布 StepRetryRequested
  skip 步骤名               发布 StepSkipped
  help                      显示帮助
""".strip()


def main() -> None:
    config = load_config()
    configure_logging(getattr(logging, str(getattr(config, "LOG_LEVEL", "INFO")).upper(), logging.INFO))
    app = RuntimeApp(config).build()
    app.start()
    print(HELP)
    try:
        while True:
            try:
                line = input("sylphos> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line == "q":
                break
            if line == "help":
                print(HELP); continue
            if line == "w":
                app.event_bus.publish(WakeWordDetected(name="manual", score=1.0, source="console")); continue
            if line == "r":
                app.event_bus.publish(ResumeWakeWordRequested(source="console")); continue
            if line == "p":
                app.event_bus.publish(PauseWakeWordRequested(source="console")); continue
            if line == "c":
                app.event_bus.publish(CancelCurrentTaskRequested(source="console")); continue
            if line == "state":
                print(json.dumps(app.context_snapshot(), ensure_ascii=False, default=str, indent=2)); continue
            if line.startswith("t "):
                app.event_bus.publish(TextInputReceived(line[2:].strip(), source="console")); continue
            if line.startswith("asr "):
                app.event_bus.publish(ASRCompleted(text=line[4:].strip(), source="console")); continue
            if line.startswith("utt "):
                app.event_bus.publish(UserUtteranceReady(line[4:].strip(), source="console")); continue
            if line.startswith("tts "):
                app.event_bus.publish(TTSRequested(line[4:].strip(), source="console")); continue
            if line.startswith("ui "):
                app.event_bus.publish(UIMessageRequested(line[3:].strip(), source="console")); continue
            if line.startswith("jump "):
                app.event_bus.publish(RuntimeJumpRequested(line[5:].strip(), source="console")); continue
            if line.startswith("retry "):
                app.event_bus.publish(StepRetryRequested(line[6:].strip(), source="console")); continue
            if line.startswith("skip "):
                app.event_bus.publish(StepSkipped(line[5:].strip(), source="console")); continue
            if line.startswith("exec "):
                # Keep JSON with spaces by slicing after tool name.
                _, rest = line.split(" ", 1)
                tool, json_text = (rest.split(" ", 1) + ["{}"])[0:2] if " " in rest else (rest, "{}")
                try:
                    params = json.loads(json_text)
                except json.JSONDecodeError as exc:
                    print(f"参数 JSON 解析失败: {exc}"); continue
                app.event_bus.publish(ToolExecutionRequested(tool, params, source="console")); continue
            print("未知命令，输入 help 查看帮助")
    except KeyboardInterrupt:
        print("\n收到 Ctrl+C，正在退出 ...")
    finally:
        app.close()


if __name__ == "__main__":
    main()
