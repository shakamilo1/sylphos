Sylphos（当前仓库版本）使用说明
=================================

本说明只覆盖当前仓库里已经存在、并可直接运行的内容。

一、项目当前结构（与语音链路相关）
--------------------------------
1) 配置
- config/voice.py：默认配置（项目内基线）
- config/local_config.py：本地覆盖配置（由配置向导生成）

2) 正式运行入口
- scripts/run_wakeword_pipeline.py：wakeword + 录音正式入口

3) 配置向导
- scripts/setup_wakeword.py：交互式生成 config/local_config.py

4) 统一测试入口
- scripts/test_wakeword_pipeline.py：统一测试脚本（设备/模型/配置/录音/唤醒/全链路）

5) 核心模块
- voice/audio/hub.py：麦克风采集与音频分发
- voice/audio/recorder.py：定时录音 + VAD 自动结束录音
- voice/wakeword/openwakeword_engine.py：OpenWakeWord 适配
- sylphos/runtime/orchestrator.py：wakeword 与录音事件编排

6) 旧测试脚本（仍保留）
- test_openwakeword_win11.py
- voice/VAD/test_silero_vad.py
- detect_from_microphone.py（示例来源脚本，默认依赖 pyaudio）

二、环境准备（Windows + 项目内 .venv）
--------------------------------------
1) 进入项目目录
- cd /d H:\\path\\to\\sylphos

2) 创建虚拟环境
- py -3.11 -m venv .venv

3) 激活虚拟环境（PowerShell）
- .\\.venv\\Scripts\\Activate.ps1

4) 安装依赖
- python -m pip install --upgrade pip
- pip install -r requirements.txt

说明：当前仓库 requirements.txt 采用 UTF-16 编码保存；如果你的 pip 在某些环境读取失败，先将其转成 UTF-8 再安装。

三、模型下载
-----------
当前仓库提供下载脚本：
- python download.py

脚本会调用 openwakeword 的下载函数，把模型放到 openwakeword 包目录下的：
- .../site-packages/openwakeword/resources/models

若你使用 project_relative 模式（配置里 WAKEWORD_MODEL_SOURCE=project_relative），模型相对路径统一按“项目根目录”解析；例如：
- models/wakeword/your_model.onnx
会被解析为：<项目根目录>/models/wakeword/your_model.onnx

四、配置覆盖关系
---------------
1) 项目先加载 config/voice.py 中的默认值
2) 若存在 config/local_config.py，则用同名变量覆盖默认值

也就是说：
- voice.py 是“默认值”
- local_config.py 是“本机实际生效值”

五、运行配置向导
---------------
1) 命令
- python -m scripts.setup_wakeword

2) 向导可配置项（当前已支持）
- 输入设备（索引/默认）
- 输入采样率
- 声道数 / blocksize / dtype
- wakeword 模型来源（openwakeword_resource / project_relative）
- wakeword 模型文件
- 唤醒阈值
- 冷却时间
- 录音保存目录
- 录音保存模式（off/latest/archive）
- 固定时长录音参数（COMMAND_RECORD_SECONDS）
- VAD 开关
- VAD 参数（threshold/min_speech/min_silence/speech_pad/end_silence/prebuffer/check_interval/sample_rate）

3) 输出
- 自动写入 config/local_config.py

六、统一测试脚本用法
-------------------
统一测试入口：
- python -m scripts.test_wakeword_pipeline <子命令>

可用子命令：
1) 查看设备
- python -m scripts.test_wakeword_pipeline list-devices

2) 查看模型
- python -m scripts.test_wakeword_pipeline list-models

3) 打印当前配置
- python -m scripts.test_wakeword_pipeline show-config

4) 配置自检
- python -m scripts.test_wakeword_pipeline check-config

5) 测试定时录音
- python -m scripts.test_wakeword_pipeline test-timed-record --duration 3

6) 测试 VAD 录音
- python -m scripts.test_wakeword_pipeline test-vad-record --duration 12

7) 测试唤醒监听
- python -m scripts.test_wakeword_pipeline test-wakeword-listen --duration 15

8) 测试完整链路
- python -m scripts.test_wakeword_pipeline test-full-pipeline --duration 20

七、正式运行
-----------
命令：
- python -m scripts.run_wakeword_pipeline

运行行为（当前实现）：
1) 监听 wakeword
2) 命中后暂停 wakeword
3) 触发一次录音（定时模式或 VAD 模式）
4) 录音完成后不会自动恢复 wakeword
5) 终端输入 r + 回车可手动恢复监听

八、定时录音与 VAD 录音说明
-------------------------
1) 定时录音
- 条件：COMMAND_RECORD_SECONDS > 0
- 行为：固定时长后结束并保存

2) VAD 录音
- 条件：COMMAND_RECORD_SECONDS <= 0 且 VAD_ENABLED=True
- 行为：检测到说话后开始，持续静音达到 VAD_END_SILENCE_MS 后结束

九、常见问题排查
---------------
1) 启动时报“模型不存在”
- 先运行 python download.py
- 或检查 project_relative 路径是否真实存在

2) 唤醒没触发
- 降低 WAKEWORD_THRESHOLD（例如 0.5 -> 0.35）
- 用 list-devices 确认设备索引
- 检查采样率、麦克风系统权限

3) VAD 一直不结束
- 增大 VAD_THRESHOLD（减少背景噪声误判）
- 减小 VAD_END_SILENCE_MS（更快判定结束）

4) 录音文件未生成
- 检查 RECORD_SAVE_MODE 是否为 off
- 检查 RECORDINGS_DIR 是否可写

十、当前未实现 / 仅保留行为
----------------------------
1) 当前全链路录音完成后“自动恢复唤醒”未实现，仍为手动恢复（输入 r）
2) 仓库中旧测试脚本仍可单独使用，但建议优先使用统一测试入口
