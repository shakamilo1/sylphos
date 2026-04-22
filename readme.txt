Sylphos 当前版本使用说明（语音链路）
====================================

> 本文档只描述当前仓库已经实现并可直接使用的能力，不讨论未来规划。

一、项目简介
-----------
当前仓库已实现一条可运行的 wakeword + 录音链路，核心能力包括：
1) 麦克风音频采集与分发（AudioHub）
2) OpenWakeWord 唤醒词检测
3) 录音（固定时长模式 + VAD 自动结束模式）
4) 统一配置向导（生成本地配置）
5) 统一测试入口（设备/模型/配置/录音/唤醒/全链路）

二、语音链路相关目录与脚本
------------------------
- `config/voice.py`：默认配置
- `config/local_config.py`：本地覆盖配置（由向导生成）

- `scripts/setup_wakeword.py`：配置向导
- `scripts/test_wakeword_pipeline.py`：统一测试 CLI
- `scripts/run_wakeword_pipeline.py`：正式运行入口
- `scripts/runtime_bootstrap.py`：运行链路装配逻辑（供 run/test 复用）

- `voice/audio/hub.py`：音频输入与广播
- `voice/audio/recorder.py`：录音服务（定时 + VAD）
- `voice/wakeword/openwakeword_engine.py`：OpenWakeWord 适配
- `sylphos/runtime/orchestrator.py`：事件编排

- `download.py`：下载 openwakeword 模型

旧脚本（仍保留，主要用于历史/单点调试）：
- `test_openwakeword_win11.py`
- `voice/VAD/test_silero_vad.py`
- `detect_from_microphone.py`（示例脚本，额外依赖 `pyaudio`）

三、从零开始安装（Windows + 项目内 .venv）
----------------------------------------
### 1) 拉取仓库
```bash
git clone <你的仓库地址>
```

### 2) 进入项目目录
```bash
cd sylphos
```

### 3) 创建虚拟环境
```bash
py -3.11 -m venv .venv
```

### 4) 激活虚拟环境（PowerShell）
```powershell
.\.venv\Scripts\Activate.ps1
```

如果你用的是 CMD：
```bat
.\.venv\Scripts\activate.bat
```

### 5) 安装依赖
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

说明：当前 `requirements.txt` 已是 **UTF-8（无 BOM）**，可直接用于 `pip install -r requirements.txt`。

### 6) 依赖分层说明（主链路 / 旧脚本）
主链路直接依赖（已写入 requirements.txt）：
- `openwakeword`、`onnxruntime`
- `numpy`
- `sounddevice`
- `silero-vad`
- `scipy`（重采样回退路径，保证无需额外本地编译也可运行）

可选依赖（默认不放入 requirements.txt）：
- `samplerate`：重采样性能优化项；未安装时代码会自动回退到 `scipy`。
- `soundfile`：仅旧脚本 `voice/VAD/test_silero_vad.py` 直接使用。
- `pyaudio`：仅旧示例 `detect_from_microphone.py` 使用。

四、模型下载与模型放置
--------------------
### 1) 下载内置模型
```bash
python download.py
```

该脚本会调用 openwakeword 的下载函数，模型会下载到 openwakeword 包目录，例如：
- `.../site-packages/openwakeword/resources/models`

### 2) project_relative 模式放置方式
当 `WAKEWORD_MODEL_SOURCE = "project_relative"` 时，
`WAKEWORD_MODEL_RELATIVE_PATH` 统一按“项目根目录”解析。

例如配置：
- `WAKEWORD_MODEL_RELATIVE_PATH = "models/wakeword/your_model.onnx"`

实际路径应为：
- `<项目根目录>/models/wakeword/your_model.onnx`

五、配置覆盖关系（非常重要）
-----------------------
配置加载顺序：
1) 先加载 `config/voice.py` 默认值
2) 若存在 `config/local_config.py`，同名配置覆盖默认值

结论：
- `voice.py`：默认配置模板
- `local_config.py`：当前机器最终生效配置

六、运行配置向导
-------------
```bash
python -m scripts.setup_wakeword
```

向导会覆盖/写入 `config/local_config.py`，主要包含：
- 输入设备、采样率、声道、blocksize、dtype
- wakeword 模型来源与模型文件
- 唤醒阈值、冷却时间
- 录音保存目录/保存模式
- 定时录音参数
- VAD 开关与各项参数

提示：若你设置 `COMMAND_RECORD_SECONDS <= 0` 且 `VAD_ENABLED=False`，向导会阻止写入并提示修正。

七、统一测试 CLI
--------------
统一入口：
```bash
python -m scripts.test_wakeword_pipeline --help
```

### 常用命令（建议按顺序）
1) 打印当前配置
```bash
python -m scripts.test_wakeword_pipeline show-config
```

2) 配置自检
```bash
python -m scripts.test_wakeword_pipeline check-config
```

3) 查看设备
```bash
python -m scripts.test_wakeword_pipeline list-devices
```

4) 查看模型
```bash
python -m scripts.test_wakeword_pipeline list-models
```

5) 定时录音测试
```bash
python -m scripts.test_wakeword_pipeline test-timed-record --duration 3
```

6) VAD 录音测试
```bash
python -m scripts.test_wakeword_pipeline test-vad-record --duration 12
```

7) 全链路测试
```bash
python -m scripts.test_wakeword_pipeline test-full-pipeline --duration 20
```

### 每个子命令用途
- `list-devices`：列出可用输入设备
- `list-models`：列出 openwakeword 内置模型；若当前配置是 `project_relative`，会额外打印解析后的配置路径
- `show-config`：显示当前生效配置值
- `check-config`：检查关键配置与模型路径是否可用
- `test-timed-record`：仅测试固定时长录音
- `test-vad-record`：仅测试 VAD 录音
- `test-wakeword-listen`：仅测试唤醒监听
- `test-full-pipeline`：测试唤醒->录音完整链路

八、正式运行
-----------
```bash
python -m scripts.run_wakeword_pipeline
```

当前行为：
1) 持续监听 wakeword
2) 命中后暂停 wakeword
3) 触发一次录音（定时或 VAD）
4) 录音完成后不会自动恢复唤醒
5) 终端输入 `r` + 回车可手动恢复监听

九、定时录音与 VAD 录音切换
------------------------
在配置中通过 `COMMAND_RECORD_SECONDS` 控制：
- `> 0`：固定时长录音
- `<= 0`：进入 VAD 模式（此时 `VAD_ENABLED` 必须为 `True`）

十、常见问题排查
--------------
1) `ModuleNotFoundError`（如 sounddevice/openwakeword）
- 确认已激活 `.venv`
- 重新执行 `pip install -r requirements.txt`

2) `check-config` 报模型不存在
- 先执行 `python download.py`
- 若是 `project_relative`，检查路径是否相对项目根目录

3) 唤醒不稳定
- 适当降低 `WAKEWORD_THRESHOLD`
- 检查输入设备是否选择正确
- 检查系统麦克风权限

4) VAD 迟迟不结束
- 适当提高 `VAD_THRESHOLD`
- 适当降低 `VAD_END_SILENCE_MS`

5) 录音没保存
- 检查 `RECORD_SAVE_MODE` 是否为 `off`
- 检查 `RECORDINGS_DIR` 是否可写

十一、当前仍需手动处理/已知行为
----------------------------
1) 全链路中录音完成后默认不自动恢复唤醒，需要手动输入 `r` 恢复。
2) 旧测试脚本仍保留，但建议优先使用统一测试 CLI（`scripts/test_wakeword_pipeline.py`）。

