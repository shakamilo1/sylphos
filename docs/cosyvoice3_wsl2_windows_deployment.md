# 在 WSL2 上部署 CosyVoice3 并让 Windows Sylphos 调用

本文档说明如何在 Windows + WSL2 Ubuntu 环境中部署 CosyVoice3，并通过 FastAPI 服务向 Windows 端 Sylphos 主程序提供语音合成能力。部署完成后，CosyVoice3 在 WSL2 中使用 GPU 推理，Windows 端 Sylphos 通过 HTTP 调用 `http://127.0.0.1:9880/v1/tts`，获得生成的 WAV 音频并在 Windows 本地播放。

---

## 1. 部署目标与整体架构

### 1.1 部署目标

本部署章节的目标是完成以下能力：

1. 在 WSL2 Ubuntu 中安装 CosyVoice3 运行环境。
2. 使用 Conda 创建独立 Python 环境，避免与 Sylphos 主程序环境冲突。
3. 下载并管理 CosyVoice3 Base 模型、RL 模型权重和 `ttsfrd` 前端资源。
4. 在 WSL2 中启动 CosyVoice3 FastAPI 服务。
5. Windows 端 Sylphos 通过 HTTP 请求调用 WSL2 服务，并播放返回的 WAV 音频。

### 1.2 调用链路

整体调用链路如下：

```text
Windows Sylphos 主程序
        │
        │ HTTP POST /v1/tts
        ▼
WSL2 Ubuntu FastAPI 服务（端口 9880）
        │
        │ 调用 CosyVoice3 模型推理
        ▼
WSL2 GPU / CUDA / PyTorch
        │
        │ 生成 WAV 音频
        ▼
FastAPI 返回 WAV 数据或音频路径
        │
        ▼
Windows Sylphos 保存并播放 WAV 文件
```

### 1.3 推荐目录结构

本文档使用如下目录结构作为示例：

```text
~
├── CosyVoice/                                      # CosyVoice 官方仓库
└── sylphos_services/
    └── cosyvoice3/
        ├── cosyvoice_server.py                     # FastAPI 服务入口
        ├── outputs/                                # 服务生成的临时音频目录
        └── pretrained_models/
            ├── Fun-CosyVoice3-0.5B                 # Base 模型目录，实际传给 AutoModel 的 model_dir
            ├── Fun-CosyVoice3-0.5B-rl              # RL 模型目录，复制后替换 llm.pt
            ├── CosyVoice-ttsfrd                    # ttsfrd 前端资源和 wheel 包
            ├── CosyVoice2-0.5B                     # 可选兼容模型目录
            ├── base -> Fun-CosyVoice3-0.5B         # 管理用软链接，不直接传给 AutoModel
            └── rl -> Fun-CosyVoice3-0.5B-rl        # 管理用软链接，不直接传给 AutoModel
```

> 说明：路径可以根据实际机器调整，但建议将模型和服务文件集中放在 `~/sylphos_services/cosyvoice3`，便于管理、备份和排查问题。

---

## 2. WSL2 与 GPU 环境准备

### 2.1 Windows 侧准备

在 Windows 侧需要先完成以下准备：

1. 启用 WSL2。
2. 安装 Ubuntu 24.04 或其他兼容的 Ubuntu 发行版。
3. 安装支持 WSL CUDA 的 NVIDIA 显卡驱动。
4. 确认 Windows 端能够正常识别 NVIDIA GPU。

可在 Windows PowerShell 中检查 WSL 状态：

```powershell
wsl --status
wsl --list --verbose
```

可在 Windows PowerShell 中检查 GPU 驱动状态：

```powershell
nvidia-smi
```

如果 `nvidia-smi` 能正常显示显卡信息、驱动版本和 CUDA 版本，说明 Windows 侧 GPU 驱动基本可用。

### 2.2 WSL2 Ubuntu 基础检查

进入 WSL2 Ubuntu 后，先确认内核版本：

```bash
uname -r
```

确认 WSL2 中是否能识别 NVIDIA GPU：

```bash
nvidia-smi
```

如果 WSL2 中也能正常显示 GPU 信息，说明 WSL2 CUDA 转发可用。

> 注意：WSL2 中通常不需要单独安装 Linux 版 NVIDIA 驱动。GPU 驱动主要安装在 Windows 侧，WSL2 通过 Windows 驱动提供 CUDA 能力。

### 2.3 安装基础工具和系统依赖

更新 apt 软件源并安装基础依赖：

```bash
sudo apt update
sudo apt install -y git git-lfs ffmpeg sox libsox-dev build-essential curl
```

初始化 Git LFS：

```bash
git lfs install
```

各依赖用途说明：

| 依赖 | 用途 |
| --- | --- |
| `git` | 克隆 CosyVoice 官方仓库 |
| `git-lfs` | 支持大文件下载，部分模型或资源可能依赖 LFS |
| `ffmpeg` | 音频格式处理 |
| `sox` / `libsox-dev` | 音频处理依赖 |
| `build-essential` | 编译 Python 原生扩展依赖 |
| `curl` | 健康检查和接口调试 |

---

## 3. 安装 Conda 并创建 Python 环境

### 3.1 安装 Conda

如果 WSL2 中尚未安装 Conda，可安装 Miniconda 或 Anaconda。以下以 Miniconda 为例：

```bash
cd ~
curl -fsSLO https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh
```

安装过程中按提示确认安装路径。安装完成后，重新打开 WSL2 终端，或执行以下命令加载 Conda：

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda init bash
```

检查 Conda 是否安装成功：

```bash
conda --version
```

### 3.2 创建 CosyVoice3 专用环境

创建名为 `cosyvoice3` 的 Conda 环境：

```bash
conda create -n cosyvoice3 python=3.10 -y
```

激活环境：

```bash
conda activate cosyvoice3
```

确认 Python 版本：

```bash
python --version
```

推荐使用 Python 3.10，是因为 CosyVoice、PyTorch、音频依赖和部分推理依赖在该版本下兼容性更稳定。

### 3.3 升级 pip 并限制 setuptools 版本

升级 pip 和 wheel：

```bash
python -m pip install -U pip wheel
```

安装兼容版本的 setuptools：

```bash
python -m pip install "setuptools<70"
```

部分语音模型依赖或旧版 Python 构建脚本可能与较新的 setuptools 存在兼容问题，因此建议将 setuptools 限制在 70 以下。

---

## 4. 获取 CosyVoice3 仓库并先安装项目依赖

### 4.1 克隆 CosyVoice 官方仓库

进入用户主目录并克隆仓库：

```bash
cd ~
git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git
cd CosyVoice
```

如果已经克隆但子模块不完整，可执行：

```bash
git submodule update --init --recursive
```

### 4.2 先安装 CosyVoice requirements

实际跑通流程中，**应先安装 CosyVoice 仓库 requirements，再最后安装 RTX 5080 所需的 PyTorch CUDA 12.8 版本**。原因是 CosyVoice 的 `requirements.txt` 可能会固定或间接安装较旧的 `torch==2.3.1+cu121`、`torchaudio`、`torchvision` 或 `triton`，如果先安装 `torch==2.8.0+cu128`，后续执行 requirements 可能把 PyTorch 降级，导致 RTX 5080 出现 `sm_120 incompatible` 等兼容性警告。

在 `cosyvoice3` Conda 环境中执行：

```bash
cd ~/CosyVoice
pip install -r requirements.txt
```

如果后续启动 FastAPI 服务，需要安装服务依赖：

```bash
pip install fastapi uvicorn python-multipart soundfile modelscope
```

如仓库说明要求以可编辑模式安装，也可执行：

```bash
pip install -e .
```

### 4.3 处理 openai-whisper / pkg_resources 兼容问题

如果安装依赖时遇到 `openai-whisper`、`pkg_resources`、`setuptools` 或构建隔离相关问题，可按以下方式处理：

```bash
python -m pip install "setuptools<70"
pip install --no-build-isolation openai-whisper
```

如果某个依赖包在构建阶段仍然因为隔离环境找不到已安装依赖，也可以对该依赖使用同样的 `--no-build-isolation` 思路处理。处理完成后，再回到 `~/CosyVoice` 执行 requirements 或可编辑安装命令。

> 注意：不同版本的 CosyVoice 仓库依赖文件可能有所变化，应优先参考当前仓库的官方说明。本文档记录的是 Sylphos 最终跑通 CosyVoice3 + RTX 5080 + WSL2 的实际安装顺序。

---

## 5. 最后安装 RTX 5080 可用的 PyTorch CUDA 12.8

### 5.1 卸载 requirements 可能安装的旧版 PyTorch

完成 CosyVoice requirements 安装后，再卸载旧版 PyTorch 相关包，避免保留 `torch==2.3.1+cu121`、旧版 `torchaudio`、`torchvision` 或 `triton`：

```bash
pip uninstall -y torch torchaudio torchvision triton
```

### 5.2 安装 CUDA 12.8 版本 PyTorch

本部署最终使用与 RTX 5080 兼容的 PyTorch 2.8.0 + CUDA 12.8：

```bash
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

> 说明：RTX 5080 对应新一代 GPU 架构。旧版 CUDA 12.1 PyTorch 轮子可能无法完整支持该显卡算力，实际部署中应以 `cu128` 轮子为准。

### 5.3 验证 CUDA 可用性

在 Conda 环境中运行以下命令，检查 PyTorch 是否可以使用 GPU：

```bash
python -c "import torch; print('torch:', torch.__version__); print('cuda available:', torch.cuda.is_available()); print('device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

继续执行 CUDA 矩阵乘法测试：

```bash
python -c "import torch; x=torch.randn(1024,1024,device='cuda'); y=x@x; print('cuda matmul ok:', y.shape)"
```

如果输出中包含 `cuda matmul ok`，且不再出现 RTX 5080 / `sm_120 incompatible` 相关警告，说明 PyTorch CUDA 12.8 已经正确覆盖旧版本，后续 CosyVoice3 可以使用 GPU 推理。

---

## 6. 下载 CosyVoice3 模型与 ttsfrd 资源

### 6.1 创建模型目录

创建 Sylphos 专用模型目录：

```bash
mkdir -p ~/sylphos_services/cosyvoice3/pretrained_models
cd ~/sylphos_services/cosyvoice3
```

### 6.2 使用 ModelScope CLI 下载模型

可以使用 ModelScope CLI 下载 CosyVoice3 主模型和 ttsfrd 资源：

```bash
modelscope download --model FunAudioLLM/Fun-CosyVoice3-0.5B-2512 --local_dir ~/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B
modelscope download --model iic/CosyVoice-ttsfrd --local_dir ~/sylphos_services/cosyvoice3/pretrained_models/CosyVoice-ttsfrd
modelscope download --model iic/CosyVoice2-0.5B --local_dir ~/sylphos_services/cosyvoice3/pretrained_models/CosyVoice2-0.5B
```

其中 `Fun-CosyVoice3-0.5B` 是最终 Base 推理使用的主目录。`llm.rl.pt` 会随 CosyVoice3 主模型一起下载，后续 RL 版本通过复制目录并将 `llm.rl.pt` 替换为 `llm.pt` 启用。

### 6.3 使用 snapshot_download 下载模型

实际部署中也可以使用 Python 的 `snapshot_download` 下载模型。该方式便于写入一次性下载脚本或在 Conda 环境中直接执行：

```bash
cd ~/sylphos_services/cosyvoice3
python -c "from modelscope import snapshot_download; snapshot_download('FunAudioLLM/Fun-CosyVoice3-0.5B-2512', local_dir='pretrained_models/Fun-CosyVoice3-0.5B'); snapshot_download('iic/CosyVoice-ttsfrd', local_dir='pretrained_models/CosyVoice-ttsfrd'); snapshot_download('iic/CosyVoice2-0.5B', local_dir='pretrained_models/CosyVoice2-0.5B')"
```

等价的下载逻辑如下，适合记录到部署脚本中：

```text
from modelscope import snapshot_download
snapshot_download("FunAudioLLM/Fun-CosyVoice3-0.5B-2512", local_dir="pretrained_models/Fun-CosyVoice3-0.5B")
snapshot_download("iic/CosyVoice-ttsfrd", local_dir="pretrained_models/CosyVoice-ttsfrd")
snapshot_download("iic/CosyVoice2-0.5B", local_dir="pretrained_models/CosyVoice2-0.5B")
```

下载完成后，CosyVoice3 主模型目录中应包含 Base 权重和 RL 权重相关文件：

| 文件 | 说明 |
| --- | --- |
| `llm.pt` | 默认 Base 推理权重 |
| `llm.rl.pt` | RL 推理权重，随 CosyVoice3 主模型一起下载 |
| 其他配置文件 | 模型结构、tokenizer、frontend 等配置 |

### 6.4 解压并安装 ttsfrd

仅下载 `CosyVoice-ttsfrd` 目录还不够，还需要解压资源包并安装其中的 wheel 包：

```bash
cd ~/sylphos_services/cosyvoice3/pretrained_models/CosyVoice-ttsfrd
unzip -o resource.zip -d .
pip install ttsfrd_dependency-0.1-py3-none-any.whl
pip install ttsfrd-0.4.2-cp310-cp310-linux_x86_64.whl
```

安装成功后，CosyVoice3 启动或推理日志中可看到类似信息：

```text
use ttsfrd frontend
```

这表示 CosyVoice3 已启用 ttsfrd 前端，可改善数字、符号、英文混读和复杂文本的规范化效果。

---

## 7. Base / RL 模型目录管理

### 7.1 使用标准目录名作为 AutoModel 的 model_dir

最终跑通时发现，CosyVoice3 `AutoModel` 对 `model_dir` 的目录名识别较敏感。如果传入过于简化的软链接目录，例如 `pretrained_models/base` 或 `pretrained_models/rl`，曾出现如下错误：

```text
TypeError: No valid model type found
```

因此，服务端实际传给 `AutoModel` 的 `model_dir` 应使用包含模型名称的标准目录，例如：

```text
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B-rl
```

其中：

| 目录 | 用途 | 是否直接传给 AutoModel |
| --- | --- | --- |
| `Fun-CosyVoice3-0.5B` | Base 模型，保留下载后的默认 `llm.pt` | 是 |
| `Fun-CosyVoice3-0.5B-rl` | RL 模型，复制 Base 目录后替换 `llm.pt` | 是 |
| `base` / `rl` 软链接 | 人工管理和快速查看用途 | 不建议直接传给 AutoModel |

### 7.2 创建 RL 模型目录并替换权重

复制一份 CosyVoice3 主模型目录作为 RL 目录：

```bash
cd ~/sylphos_services/cosyvoice3/pretrained_models
cp -a Fun-CosyVoice3-0.5B Fun-CosyVoice3-0.5B-rl
```

进入 RL 目录：

```bash
cd ~/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B-rl
```

备份原 Base 权重：

```bash
mv llm.pt llm.base.pt
```

将 RL 权重复制为服务默认读取的 `llm.pt`：

```bash
cp llm.rl.pt llm.pt
```

切换后，`Fun-CosyVoice3-0.5B-rl` 目录中的 `llm.pt` 即为 RL 权重。Base 版本仍使用原始目录：

```text
~/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B
```

### 7.3 保留软链接作为管理手段

可以保留软链接帮助人工管理目录，但不要把软链接路径作为 `AutoModel` 的实际 `model_dir`：

```bash
cd ~/sylphos_services/cosyvoice3/pretrained_models
ln -sfn Fun-CosyVoice3-0.5B base
ln -sfn Fun-CosyVoice3-0.5B-rl rl
```

软链接用途如下：

| 软链接 | 指向 | 用途 |
| --- | --- | --- |
| `base` | `Fun-CosyVoice3-0.5B` | 便于人工识别 Base 目录 |
| `rl` | `Fun-CosyVoice3-0.5B-rl` | 便于人工识别 RL 目录 |

### 7.4 最终模型目录检查

检查模型目录和软链接：

```bash
find ~/sylphos_services/cosyvoice3/pretrained_models -maxdepth 2 \
  \( -type f \( -name "llm.pt" -o -name "llm.rl.pt" -o -name "llm.base.pt" \) -o -type l \) \
  -print
```

期望至少看到类似文件：

```text
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B/llm.pt
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B/llm.rl.pt
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B-rl/llm.base.pt
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B-rl/llm.pt
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/base
/home/<user>/sylphos_services/cosyvoice3/pretrained_models/rl
```

---

## 8. 本地最小推理验证

在启动 FastAPI 服务前，建议先在 WSL2 中完成一次本地推理验证，确认模型、依赖和 GPU 均正常。

### 8.1 创建本地推理验证脚本

在 CosyVoice 仓库目录中创建本地验证脚本：

```bash
cd ~/CosyVoice
nano run_cosyvoice3_local.py
```

验证脚本应完成以下功能：

1. 读取本地 Base 或 RL 模型目录。
2. 初始化 CosyVoice3 模型。
3. 输入一段中文测试文本。
4. 生成 WAV 文件，例如 `sylphos_cosyvoice3_0.wav`。
5. 将生成文件写入当前目录或 `~/sylphos_services/cosyvoice3/outputs`。

> 本文档只说明验证脚本应具备的功能，不在此处展开 Python 代码。实际脚本应以 CosyVoice 官方仓库当前版本的推理接口为准。

### 8.2 执行本地推理测试

运行验证脚本：

```bash
python run_cosyvoice3_local.py
```

如果推理成功，应能看到生成的 WAV 文件，例如：

```text
~/CosyVoice/sylphos_cosyvoice3_0.wav
```

最终跑通时的关键现象如下：

```text
sample_rate: 24000
yield speech len ...
```

其中 `sample_rate: 24000` 表示 CosyVoice3 输出采样率为 24000 Hz，`yield speech len ...` 表示模型已经产出音频片段。只要 WAV 文件正常生成并可播放，即可认为本地最小推理通过。

### 8.3 检查生成音频

WSL2 内部可以通过文件路径查看 WAV 文件，也可以在 Windows 文件资源管理器中访问 WSL 路径。例如：

```text
\\wsl.localhost\Ubuntu-24.04\home\<user>\CosyVoice\sylphos_cosyvoice3_0.wav
```

双击 WAV 文件后，如果 Windows 默认播放器可以正常播放，说明生成音频有效。

> 第一次推理通常较慢，因为需要加载模型、初始化 CUDA、编译或缓存部分算子。模型常驻内存后，后续推理速度会明显提升。

> 如果日志中出现 ONNX Runtime `libcudnn.so.8` 相关警告，但 PyTorch CUDA 矩阵乘法测试已经通过、CosyVoice3 能输出 `yield speech len ...` 且 `sylphos_cosyvoice3_0.wav` 可以播放，则该 ONNX Runtime 警告可以暂时忽略。

---

## 9. 部署 CosyVoice3 FastAPI 服务

### 9.1 创建服务目录并准备服务脚本

Sylphos 现在在仓库中提供标准 CosyVoice3 FastAPI 服务模板：

```text
services/cosyvoice3/cosyvoice_server.py
```

`~/sylphos_services/cosyvoice3/cosyvoice_server.py` 是 WSL2 运行时服务目录中的目标位置；该文件来源于仓库模板，不需要用户凭空寻找或复制一个不存在的文件。

创建服务目录和输出目录后，从仓库复制服务脚本：

```bash
cd ~/sylphos
mkdir -p ~/sylphos_services/cosyvoice3/outputs
cp services/cosyvoice3/cosyvoice_server.py ~/sylphos_services/cosyvoice3/cosyvoice_server.py
cd ~/sylphos_services/cosyvoice3
```

也可以不复制，直接从仓库路径运行：

```bash
cd ~/sylphos/services/cosyvoice3
python cosyvoice_server.py
```

### 9.2 FastAPI 服务职责

仓库模板 `services/cosyvoice3/cosyvoice_server.py` 已包含以下能力：

1. 提供健康检查接口：`GET /health`。
2. 提供语音合成接口：`POST /tts`，并保留 `POST /v1/tts` 作为 Windows 端现有客户端兼容别名。`/v1/tts` 推荐直接返回 `audio/wav` 二进制数据，避免 Windows 端依赖 WSL2 内部文件路径。
3. 接收请求参数：
   - `text`：需要合成的文本。
   - `model_version`：可选，`base` 或 `rl`，默认 `base`。
   - `output_path`：可选，WSL2/Linux 内的 WAV 输出路径；未提供时默认写入 `~/sylphos_outputs/tts/latest_tts.wav`。
   - `prompt_wav` / `prompt_text`：可选 zero-shot 参考音频与文本；不传时使用服务默认值。
   - `voice_id`：可选，按 `{COSYVOICE_PROMPT_DIR}/{voice_id}.wav` 和 `{COSYVOICE_PROMPT_DIR}/{voice_id}.txt` 选择预置音色。
   - `speaker`：可选说话人/音色名；只有明确需要 SFT / speaker 模式时才传，默认测试不使用 `speaker="中文女"`。
4. 通过 `COSYVOICE_REPO` 指向本地 CosyVoice 官方仓库源码，并在启动时自动加入：
   - `~/CosyVoice`
   - `~/CosyVoice/third_party/Matcha-TTS`
5. 通过 `COSYVOICE_MODEL_PATH`、`COSYVOICE_RL_MODEL_PATH` 和 `COSYVOICE_DEVICE` 选择 Base / RL 模型目录与设备。
6. 直接从官方仓库导入 `from cosyvoice.cli.cosyvoice import AutoModel`，不要求 CosyVoice 已经通过 `pip install` 安装到 site-packages。
7. 默认通过 `inference_zero_shot` 调用 CosyVoice3 生成 WAV 音频；`/tts` 会以 JSON 返回 `wav_base64` 以便兼容调试和旧式调用，`/v1/tts` 会返回 `audio/wav`。
8. 在缺少 `cosyvoice` 源码、模型路径不存在、模型加载失败或合成失败时返回明确错误信息，不在服务导入阶段崩溃。

### 9.3 推荐服务配置项

`cosyvoice_server.py` 支持以下环境变量；默认值面向已经跑通的 WSL2 Ubuntu 部署路径：

```text
COSYVOICE_REPO=~/CosyVoice
COSYVOICE_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B
COSYVOICE_RL_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl
COSYVOICE_DEVICE=cuda
COSYVOICE_PROMPT_WAV=~/CosyVoice/asset/zero_shot_prompt.wav
COSYVOICE_PROMPT_TEXT=You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。
COSYVOICE_PROMPT_DIR=~/sylphos_services/cosyvoice3/prompts
COSYVOICE_HOST=0.0.0.0
COSYVOICE_PORT=9880
```

如果模型放在服务目录下，也可以显式覆盖：

```bash
export COSYVOICE_REPO=~/CosyVoice
export COSYVOICE_MODEL_PATH=~/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B
export COSYVOICE_RL_MODEL_PATH=~/sylphos_services/cosyvoice3/pretrained_models/Fun-CosyVoice3-0.5B-rl
export COSYVOICE_DEVICE=cuda
```

> 注意：`AutoModel` 对目录名识别较敏感。不要把 `pretrained_models/base` 或 `pretrained_models/rl` 这类简化软链接直接传给服务端；应传入包含模型名的真实目录，例如 `Fun-CosyVoice3-0.5B` 或 `Fun-CosyVoice3-0.5B-rl`。

默认测试链路使用 CosyVoice3 zero-shot 模式，不使用 `speaker="中文女"`。服务默认参考音频是 `COSYVOICE_PROMPT_WAV`；未设置时回退到 `COSYVOICE_REPO/asset/zero_shot_prompt.wav`，例如 `~/CosyVoice/asset/zero_shot_prompt.wav`。默认 `prompt_text` 来自 `COSYVOICE_PROMPT_TEXT`；未设置时使用：`You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。`。

环境变量只是服务启动时的默认音色配置；修改 `COSYVOICE_PROMPT_WAV`、`COSYVOICE_PROMPT_TEXT` 或 `COSYVOICE_PROMPT_DIR` 后需要重启 FastAPI 服务才会成为新的默认值。临时换发声人不需要重启服务，可以在 `/tts` 或 `/v1/tts` 请求体中直接传 `prompt_wav` / `prompt_text`，这些请求字段优先级最高。

zero-shot prompt 优先级为：

1. 请求体中的 `prompt_wav` / `prompt_text`。
2. 请求体中的 `voice_id`，解析到 `COSYVOICE_PROMPT_DIR` 下同名 `.wav` 和 `.txt`。
3. 环境变量 `COSYVOICE_PROMPT_WAV` / `COSYVOICE_PROMPT_TEXT`。
4. 内置默认 `{COSYVOICE_REPO}/asset/zero_shot_prompt.wav` 和默认 prompt text。

建议把多个音色放在：

```text
~/sylphos_services/cosyvoice3/prompts
├── female_01.wav
├── female_01.txt
├── male_01.wav
└── male_01.txt
```

然后请求中可以使用 `"voice_id": "female_01"` 来选择 `~/sylphos_services/cosyvoice3/prompts/female_01.wav` 与同名 `.txt`。如果同名 `.wav` 或 `.txt` 缺失，服务会返回 HTTP 400，并指出缺少哪个文件。

`prompt_text` 必须和 `prompt_wav` 里实际说的话完全一致。参考音频建议 3-10 秒、单人、安静、无背景音乐、语速自然。

### 9.4 启动 FastAPI 服务

推荐启动方式如下：

```bash
cd ~/sylphos_services/cosyvoice3
conda activate cosyvoice3
COSYVOICE_REPO=~/CosyVoice \
COSYVOICE_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B \
COSYVOICE_RL_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl \
uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880
```

如果已经进入 `~/sylphos_services/cosyvoice3`，且使用默认路径，也可以简化为：

```bash
uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880
```

也支持在任意目录启动，只要显式设置 `COSYVOICE_REPO`、`COSYVOICE_MODEL_PATH` 和 `COSYVOICE_RL_MODEL_PATH`，并使用可导入到 `cosyvoice_server.py` 的启动方式。

参数说明：

| 参数 | 说明 |
| --- | --- |
| `cosyvoice_server:app` | `cosyvoice_server.py` 中的 FastAPI 应用对象 |
| `--host 0.0.0.0` | 允许 WSL2 虚拟网络和 Windows 宿主机访问 |
| `--port 9880` | Sylphos 约定的 TTS 服务端口 |

如果使用 systemd 管理服务，`ExecStart` 必须指向实际存在的文件。例如已复制到运行时服务目录时：

```ini
[Service]
WorkingDirectory=/home/<user>/sylphos_services/cosyvoice3
Environment=COSYVOICE_REPO=/home/<user>/CosyVoice
Environment=COSYVOICE_MODEL_PATH=/home/<user>/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B
Environment=COSYVOICE_RL_MODEL_PATH=/home/<user>/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl
Environment=COSYVOICE_DEVICE=cuda
ExecStart=/home/<user>/miniconda3/envs/cosyvoice3/bin/uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880
```

如果选择直接从仓库运行，则将 `WorkingDirectory` 和 `ExecStart` 改为仓库中的 `services/cosyvoice3/cosyvoice_server.py`。

### 9.5 健康检查

在 WSL2 中检查服务状态：

```bash
curl http://127.0.0.1:9880/health
```

期望返回类似结果：

```json
{
  "ok": true,
  "service": "cosyvoice3",
  "cosyvoice_repo": "~/CosyVoice",
  "model_path": "~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B",
  "rl_model_path": "~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl",
  "device": "cuda",
  "python": "3.10.20",
  "cosyvoice_importable": true,
  "cosyvoice_loaded": true,
  "default_prompt_wav": "~/CosyVoice/asset/zero_shot_prompt.wav",
  "default_prompt_wav_exists": true,
  "prompt_dir": "~/sylphos_services/cosyvoice3/prompts",
  "prompt_dir_exists": true,
  "prompt_text_configured": true,
  "errors": []
}
```

如果 `/health` 返回 `cosyvoice_loaded=false` 且错误包含 `CosyVoice package is not importable`，通常说明 FastAPI 服务进程没有把 `~/CosyVoice` 加入 `PYTHONPATH` / `sys.path`。此时优先检查：

1. `COSYVOICE_REPO` 是否指向官方仓库源码，例如 `~/CosyVoice`。
2. `~/CosyVoice/cosyvoice/cli/cosyvoice.py` 是否存在。
3. `/health` 返回的错误中打印的当前 `sys.path` 是否包含 `~/CosyVoice` 和 `~/CosyVoice/third_party/Matcha-TTS`。
4. `COSYVOICE_MODEL_PATH` 是否指向真实模型目录 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B`，而不是旧的 `~/sylphos_models/Fun-CosyVoice3-0.5B`。
5. Conda 环境、`uvicorn`、CUDA / PyTorch 和端口 `9880` 是否正常。

如果在 `~/CosyVoice` 里直接运行最小推理脚本可以成功生成 WAV，但 FastAPI `/health` 失败，优先检查 `COSYVOICE_REPO`、`PYTHONPATH` / `sys.path` 和 `model_path`，不要先怀疑 GPU、模型或 PyTorch。

### 9.6 在 WSL2 中测试 TTS 接口

可以使用 curl 发送一次 TTS 请求：

```bash
curl --fail -X POST http://127.0.0.1:9880/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我是 Sylphos。","model_version":"base"}'

# Windows 端现有客户端调用的是 /v1/tts：
curl --fail -X POST http://127.0.0.1:9880/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我是 Sylphos。","model_version":"base"}' \
  --output /tmp/sylphos_tts_test.wav
```

检查输出文件：

```bash
file /tmp/sylphos_tts_test.wav
```

如果 JSON 返回 `ok: true` 且 `output_path` 指向的文件存在，说明 `/tts` 接口可用。

测试 Windows 端实际使用的 `/v1/tts` 二进制 WAV 接口时，建议加上 `--fail` 并同时记录 HTTP 状态码，避免失败 JSON 被保存成 `.wav`：

```bash
curl --fail -sS -X POST http://127.0.0.1:9880/v1/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我正在使用兼容接口。","model_version":"base"}' \
  --output /tmp/sylphos_tts_test_v1.wav \
  --write-out '\nHTTP %{http_code}\n'
file /tmp/sylphos_tts_test_v1.wav
```

`/v1/tts` 的预期行为是：成功时返回 `HTTP 200`、`Content-Type: audio/wav`，保存出来的文件应被 `file` 识别为 `RIFF/WAVE`、`audio/x-wav` 或类似 WAV 类型。

如果执行 `curl --output xxx.wav` 后，`file xxx.wav` 显示 `JSON text data`，说明服务端返回的是错误 JSON，不是音频。此时不要播放该文件，应先查看 HTTP 状态码和 JSON 的 `error` / `errors` 字段：模型未加载或导入失败通常会返回 `503 Service Unavailable`，合成过程中异常通常会返回 `500 Internal Server Error`。可以临时去掉 `--output`，或另存为 `.json` 查看 `error` 字段。

长文本可能会被 CosyVoice 在内部自动分段生成，服务端会完整消费 `inference_zero_shot` / speaker 推理接口返回的 generator，并把所有 `tts_speech` 片段按时间顺序拼接成一个 WAV 后再返回。生产使用中，超长文本仍建议 Sylphos 上层按句子或自然段切分，以便控制延迟、进度和打断；但服务端本身应能返回一次请求的完整合成结果。测试长文本时，除了检查 HTTP 200 和 WAV 文件类型，也要实际确认最后一句已经播放出来，避免只听到第一个生成片段。

---

## 10. 在 WSL2/Ubuntu 中手动启动 CosyVoice3 服务

当前推荐的稳定方案是：**在 WSL2/Ubuntu 终端中手动启动 CosyVoice3 FastAPI 服务，Windows 端只负责调用已经启动的服务并测试 TTS**。不再推荐使用 Windows 脚本自动弹出或自动启动 WSL/Ubuntu/CosyVoice 服务。

如果不想手动逐行输入 Conda 激活、环境变量和 `uvicorn` 命令，可以在 WSL2/Ubuntu 终端中运行仓库里的简化脚本：

```bash
bash scripts/start_cosyvoice3_wsl.sh
```

脚本内容保持非常简单，只做以下事情：

1. 进入 WSL2 服务目录 `~/sylphos_services/cosyvoice3`。
2. 通过 `~/anaconda3/etc/profile.d/conda.sh` 激活 Conda。
3. 激活 `cosyvoice3` 环境。
4. 设置 CosyVoice3 所需环境变量。
5. 在前台启动 `uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880`。

对应脚本为：

```bash
#!/usr/bin/env bash
set -euo pipefail

# 进入服务目录
cd ~/sylphos_services/cosyvoice3

# 激活 Conda 环境
source ~/anaconda3/etc/profile.d/conda.sh
conda activate cosyvoice3

# 设置 CosyVoice3 环境变量
export COSYVOICE_REPO=~/CosyVoice
export COSYVOICE_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B
export COSYVOICE_RL_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl
export COSYVOICE_PROMPT_DIR=~/sylphos_services/cosyvoice3/prompts

# 启动服务
uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880
```

> 注意：该脚本以前台方式运行服务。需要停止服务时，在运行脚本的 WSL2/Ubuntu 终端中按 `Ctrl+C` 即可。

服务启动后，保持该 WSL2/Ubuntu 终端窗口打开。Windows 端即可通过以下地址访问服务：

```text
http://127.0.0.1:9880/v1/tts
```

---

## 11. Windows Sylphos 端调用流程

### 11.1 调用地址

Windows 端 Sylphos 访问 WSL2 中的 FastAPI 服务地址：

```text
http://127.0.0.1:9880/v1/tts
```

在常见 WSL2 配置下，Windows 访问 `127.0.0.1:<端口>` 可以转发到 WSL2 中监听 `0.0.0.0:<端口>` 的服务。

### 11.2 请求方式

Windows Sylphos 端通过 HTTP POST 调用 `/v1/tts`。

请求体至少包含：

```json
{
  "text": "需要合成的文本",
  "model_version": "base"
}
```

其中：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `text` | string | 待合成语音的文本 |
| `model_version` | string | 模型版本，可选 `base` 或 `rl` |
| `prompt_wav` | string | 可选；临时 zero-shot 参考音频路径，优先级高于默认音色和 `voice_id` |
| `prompt_text` | string | 可选；必须与 `prompt_wav` 中实际说的话完全一致 |
| `voice_id` | string | 可选；例如 `female_01`，自动使用 `COSYVOICE_PROMPT_DIR/female_01.wav` 和 `.txt` |

临时切换发声人时，可以直接传 prompt：

```json
{
  "text": "你好，我正在临时切换音色。",
  "model_version": "base",
  "prompt_wav": "~/sylphos_services/cosyvoice3/prompts/female_01.wav",
  "prompt_text": "female_01.wav 中实际说的话"
}
```

也可以使用预置 `voice_id`：

```json
{
  "text": "你好，我正在使用 female_01 音色。",
  "model_version": "base",
  "voice_id": "female_01"
}
```

Windows 端 `TTSClient.speak(..., **extra_payload)` 已经会透传额外字段，因此可以传入 `voice_id`、`prompt_wav` 或 `prompt_text`，不需要修改 `/v1/tts` 协议。

### 11.3 响应处理流程

Windows Sylphos 端推荐按以下流程处理响应：

1. 发送 HTTP POST 请求到 `/v1/tts`。
2. 判断 HTTP 状态码是否成功。
3. 如果返回 WAV 二进制数据，则保存为本地临时 WAV 文件。
4. 如果返回 JSON，则从 JSON 中读取音频路径、音频 URL 或 Base64 音频数据。
5. 将音频保存到 Windows 临时目录，例如：

```text
%TEMP%\sylphos_tts\
```

6. 在 Windows 端默认使用 `winsound` 后台播放 WAV，像语音助手一样直接从音箱播放，不弹出播放器窗口。
7. 如果 `winsound` 播放失败，`play_backend="auto"` 会自动回退到系统默认播放器。
8. 每次合成生成新的文件名，避免多次调用时覆盖上一段语音。
9. 如果接口失败、网络异常或返回内容不是有效音频，应在 Sylphos 日志或界面中输出错误信息。

### 11.4 Base / RL 模型选择

Windows Sylphos 端只需要通过请求参数选择模型版本：

```json
{
  "text": "你好，我使用 Base 模型。",
  "model_version": "base"
}
```

或：

```json
{
  "text": "你好，我使用 RL 模型。",
  "model_version": "rl"
}
```

实际加载哪个模型目录由 WSL2 FastAPI 服务端负责，Windows 端不需要直接访问模型文件。

### 11.5 Windows 端播放说明

Windows 端拿到 WAV 文件后，`TTSClient(..., auto_play=True)` 默认使用 `play_backend="auto"`。在 Windows 上该模式会优先调用标准库 `winsound.PlaySound(..., winsound.SND_FILENAME)` 阻塞播放 WAV，因此正常情况下会直接从 Windows 音箱播放，不再弹出默认播放器窗口。

推荐流程为：

1. 将 WAV 内容写入临时文件。
2. 确认文件存在且大小大于 0。
3. Windows 上优先用 `winsound` 后台播放，保证语音播完。
4. 如果 `winsound` 播放失败，自动回退到默认播放器打开 WAV，并在 stderr 中输出可读提示。
5. macOS / Linux 仍保持原有 `open` / `xdg-open` fallback。
6. 多次调用时，每次生成独立文件名。

如果调试时希望显式打开系统默认播放器，可以创建客户端时设置：

```python
from sylphos.voice.tts import TTSClient

client = TTSClient(auto_play=True, play_backend="default_app")
client.speak("你好，我是 Sylphos。")
```

可选 `play_backend`：

| 值 | 行为 |
| --- | --- |
| `auto` | 默认值；Windows 优先 `winsound`，失败后回退默认播放器；其他系统保持原有 fallback |
| `winsound` | 强制使用 Windows `winsound` 播放；非 Windows 环境会给出清晰错误 |
| `default_app` | 使用原来的默认播放器方案：Windows `os.startfile`、macOS `open`、Linux `xdg-open` |

---

## Windows 端 PowerShell 测试命令

前提：

* WSL2/Ubuntu 中的 CosyVoice3 FastAPI 服务已经手动启动。
* 服务地址为 `http://127.0.0.1:9880/v1/tts`。
* Windows 端仓库路径为 `<repo-root>`。
* Windows 端使用 `.venv\Scripts\python.exe` 调用 `sylphos.voice.tts.TTSClient`。
* `auto_play=True` 默认优先使用 `winsound` 后台播放，不弹播放器。
* `voice_id` 可以随时切换音色，不需要重启服务。
* `speak()` 返回 Windows 临时 WAV 文件路径，通常在 `%TEMP%\sylphos_tts\` 下。

先在 Windows PowerShell 中进入 Sylphos 仓库：

```powershell
cd <repo-root>
```

### 1. Base + official 音色测试

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('这是 Windows 端 Base 模型 official 音色测试。', voice_id='official'); print(p)"
```

### 2. RL + official 音色测试

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='rl', timeout_seconds=240, auto_play=True).speak('这是 Windows 端 RL 模型 official 音色测试。', voice_id='official'); print(p)"
```

### 3. Kerrigan 音色测试

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('这是 Windows 端 Kerrigan 音色测试。', voice_id='Kerrigan'); print(p)"
```

### 4. 切回 official 音色

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('现在已经切回 official 音色。', voice_id='official'); print(p)"
```

### 5. 长文本完整播放测试

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=300, auto_play=True).speak('1.温柔正确的人总是难以生存，因为这世界既不温柔，也不正确。2.我是毁灭世界，然后创造世界的人。3.宣告，汝之身托吾麾下。吾之命运附汝剑上，响应圣杯之召唤，遵从这意志、道理者，回应我！4.倘若出生于东海的我是无名小卒的话，那么被我砍倒的你到底又是哪根地上的葱呢。', voice_id='Kerrigan'); print(p)"
```

长文本测试时要确认最后一句也被播放出来，以验证服务端已经正确拼接 CosyVoice generator 返回的多个音频片段。

### 6. 默认播放器调试模式

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True, play_backend='default_app').speak('这是默认播放器打开测试。', voice_id='official'); print(p)"
```

补充说明：

* 正常使用推荐 `play_backend='auto'`，也就是默认值。
* 如果没有弹播放器但音箱直接发声，说明 `winsound` 后台播放正常。
* 如果需要确认 WAV 文件内容，可以用返回的路径手动打开。
* 如果 Windows 端报连接失败，先确认 WSL2 服务是否已经启动并监听 `0.0.0.0:9880`。
* 如果服务端返回 JSON 错误而不是音频，Windows 端应打印错误信息；不要把 JSON 当作 WAV 播放。

---

## 12. 常见问题与排查

### 12.1 WSL2 中 `nvidia-smi` 不可用

可能原因：

1. Windows 侧 NVIDIA 驱动版本过旧。
2. 未安装支持 WSL CUDA 的驱动。
3. WSL2 发行版未重启。

建议处理：

```powershell
wsl --shutdown
```

然后重新打开 Ubuntu，再执行：

```bash
nvidia-smi
```

### 12.2 PyTorch 显示 CUDA 不可用

检查命令：

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
```

如果返回 `False`，重点检查：

1. 是否安装了 CPU 版 PyTorch。
2. PyTorch CUDA 版本是否与驱动兼容。
3. 是否在正确的 Conda 环境中运行。
4. WSL2 中 `nvidia-smi` 是否正常。

### 12.3 模型下载不完整

如果模型目录缺少 `llm.pt`、`llm.rl.pt` 或配置文件，可能是下载中断或 Git LFS / ModelScope 下载异常。

建议重新下载到新的临时目录，确认完整后再替换旧目录。

### 12.4 FastAPI 服务无法启动

常见原因：

1. `uvicorn` 未安装。
2. `fastapi` 未安装。
3. `cosyvoice_server.py` 文件名、来源路径或应用对象名称不正确；请确认它来自仓库的 `services/cosyvoice3/cosyvoice_server.py`。
4. 模型路径配置错误。
5. Python 当前工作目录不正确。

检查当前目录：

```bash
pwd
```

检查服务文件，并在缺失时从仓库模板复制：

```bash
ls -lh ~/sylphos_services/cosyvoice3/cosyvoice_server.py
cp ~/sylphos/services/cosyvoice3/cosyvoice_server.py ~/sylphos_services/cosyvoice3/cosyvoice_server.py
```

检查端口占用：

```bash
ss -ltnp | grep 9880
```

### 12.5 Windows 无法访问 `127.0.0.1:9880`

建议排查：

1. 确认 WSL2 服务启动时使用 `--host 0.0.0.0`。
2. 确认服务端口为 `9880`。
3. 在 WSL2 中先执行健康检查。
4. 在 Windows PowerShell 中执行：

```powershell
curl http://127.0.0.1:9880/health
```

如果 Windows 仍无法访问，可查询 WSL2 IP 并尝试直接访问：

```bash
hostname -I
```

假设 WSL2 IP 为 `172.xx.xx.xx`，Windows 端可临时访问：

```text
http://172.xx.xx.xx:9880/health
```

### 12.6 第一次推理非常慢

这是正常现象。第一次请求通常会触发：

1. 模型加载。
2. CUDA 初始化。
3. 算子缓存或图优化。
4. 文本前端初始化。

服务常驻后，后续请求会更快。建议在 Sylphos 正式使用前先执行一次短文本预热请求。

### 12.7 ONNX Runtime 警告

部署过程中可能出现 ONNX Runtime 相关警告。如果 PyTorch CUDA 推理已经成功，并且 WAV 能正常生成，此类警告通常可以暂时忽略。后续如需优化启动速度或推理性能，再单独处理 ONNX Runtime 配置。

### 12.8 `/health` 中 `cosyvoice_importable=false`

排查：

1. 检查 `COSYVOICE_REPO` 是否指向 `~/CosyVoice`。
2. 检查 `~/CosyVoice/cosyvoice/cli/cosyvoice.py` 是否存在。
3. 查看 `/health` 错误中打印的 `sys.path` 是否包含 CosyVoice 仓库和 `third_party/Matcha-TTS`。

### 12.9 `/health` 中 `cosyvoice_loaded=false`

排查：

1. 检查 `model_path` 是否存在。
2. 检查模型目录名是否包含 `Fun-CosyVoice3-0.5B`。
3. 不要把简化软链接 `base` / `rl` 直接传给 `AutoModel`。
4. 检查 PyTorch / CUDA 是否可用。

### 12.10 `CosyVoice3.__init__() got an unexpected keyword argument 'device'`

不要把 `device` 参数传给 `AutoModel` 或 `CosyVoice3` 构造函数。`COSYVOICE_DEVICE` 目前只用于 `/health` 诊断和未来扩展。

### 12.11 错误 `"'中文女'"`

默认链路不应使用 `speaker="中文女"`。CosyVoice3 默认应走 zero-shot：`prompt_wav` + `prompt_text` + `inference_zero_shot`。`speaker` 只用于未来明确的 SFT / speaker 模式。

### 12.12 保存出的 `.wav` 是 `JSON text data`

这说明服务端返回的是错误 JSON，不是音频。使用 `curl --fail-with-body` 查看 HTTP 状态码和 JSON `error` / `errors` 字段。成功 WAV 应为 `RIFF/WAVE`。

### 12.13 `422 Unprocessable Entity`

通常表示请求 JSON 不符合 schema。检查：

1. `text` 字段是否存在。
2. PowerShell / curl 引号是否正确转义。
3. 字段类型是否为 string，例如 `text`、`model_version`、`voice_id`、`prompt_wav`、`prompt_text`。

### 12.14 `too short than prompt text` warning

这是 CosyVoice 的质量警告，不是服务错误。它表示合成文本比 `prompt_text` 短，可能影响表现。可以忽略，或使用更短、更匹配的参考 prompt。

### 12.15 `.ogg` 改名 `.wav` 也能用

这通常是底层解码器根据文件头识别出了真实格式。不建议依赖此行为，推荐用 `ffmpeg` 转成真正 WAV：

```bash
ffmpeg -y -i input.ogg -ac 1 -ar 16000 output.wav
# 或
ffmpeg -y -i input.ogg -ac 1 -ar 24000 output.wav
```

---


## 13. PR #18 最终跑通流程与验收命令

本节记录 PR #18 在用户本机最终确认跑通的实际部署路径和验收命令。前文可作为详细背景，本节可作为合并前的标准操作清单。

### 13.1 WSL2 Ubuntu 24.04 与 Conda 环境

推荐环境：

- WSL2 Ubuntu 24.04。
- CosyVoice 官方仓库：`~/CosyVoice`。
- Sylphos CosyVoice3 服务目录：`~/sylphos_services/cosyvoice3`。
- Conda 环境名：`cosyvoice3`。
- Python：3.10。
- RTX 5080：使用 PyTorch `2.8.0` + CUDA `12.8`。

创建并激活 Conda 环境：

```bash
conda create -n cosyvoice3 python=3.10 -y
conda activate cosyvoice3
```

安装 CosyVoice requirements 后，如果 `torch`、`torchaudio`、`torchvision` 或 `triton` 被降级，应重新安装 CUDA 12.8 版本：

```bash
pip uninstall -y torch torchaudio torchvision triton
pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
```

确认 CUDA 与矩阵运算可用：

```bash
python - <<'PY'
import torch
print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())
print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")
x = torch.randn(1024, 1024, device="cuda")
y = x @ x
print("cuda matmul ok:", y.shape)
PY
```

如果 `torch.cuda.is_available()` 为 `True` 且最后输出 `cuda matmul ok`，说明 PyTorch CUDA 基本可用。

### 13.2 模型、RL 权重与 ttsfrd

最终跑通的模型路径为：

```text
~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B
~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl
```

推荐在 `~/CosyVoice` 中使用 ModelScope 下载：

```bash
cd ~/CosyVoice
python - <<'PY'
from modelscope import snapshot_download
snapshot_download("FunAudioLLM/Fun-CosyVoice3-0.5B-2512", local_dir="pretrained_models/Fun-CosyVoice3-0.5B")
snapshot_download("iic/CosyVoice-ttsfrd", local_dir="pretrained_models/CosyVoice-ttsfrd")
snapshot_download("iic/CosyVoice2-0.5B", local_dir="pretrained_models/CosyVoice2-0.5B")
PY
```

`llm.rl.pt` 会随 CosyVoice3 主模型一起下载。RL 目录可以通过复制 Base 目录后将 `llm.rl.pt` 替换为 `llm.pt`：

```bash
cd ~/CosyVoice/pretrained_models
cp -a Fun-CosyVoice3-0.5B Fun-CosyVoice3-0.5B-rl
cd Fun-CosyVoice3-0.5B-rl
cp -f llm.rl.pt llm.pt
```

`ttsfrd` 不只是下载资源，还需要安装 wheel：

```bash
cd ~/CosyVoice/pretrained_models/CosyVoice-ttsfrd
unzip -o resource.zip -d .
pip install ttsfrd_dependency-0.1-py3-none-any.whl
pip install ttsfrd-0.4.2-cp310-cp310-linux_x86_64.whl
```

安装成功并被 CosyVoice 使用时，推理日志中可能出现：

```text
use ttsfrd frontend
```

### 13.3 最终推荐服务启动命令

服务目录为：

```text
~/sylphos_services/cosyvoice3
```

推荐启动命令：

```bash
cd ~/sylphos_services/cosyvoice3
conda activate cosyvoice3

COSYVOICE_REPO=~/CosyVoice \
COSYVOICE_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B \
COSYVOICE_RL_MODEL_PATH=~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl \
COSYVOICE_PROMPT_DIR=~/sylphos_services/cosyvoice3/prompts \
uvicorn cosyvoice_server:app --host 0.0.0.0 --port 9880
```

说明：

1. `COSYVOICE_REPO` 用于把官方 CosyVoice 仓库加入 `sys.path`，因此不要求 CosyVoice 被 `pip install` 成 site-packages 包。
2. `COSYVOICE_MODEL_PATH` 是 Base 模型目录，应指向 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B`。
3. `COSYVOICE_RL_MODEL_PATH` 是 RL 模型目录，应指向 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl`。
4. `COSYVOICE_PROMPT_DIR` 是 `voice_id` 音色库目录。
5. 服务监听 `0.0.0.0:9880`，Windows 端通常可通过 `http://127.0.0.1:9880` 访问。

### 13.4 健康检查与字段含义

在 WSL2 中执行：

```bash
curl http://127.0.0.1:9880/health
```

重点检查字段：

| 字段 | 说明 |
| --- | --- |
| `ok` | 服务是否整体可用 |
| `cosyvoice_repo` | 当前服务使用的 CosyVoice 官方仓库路径 |
| `model_path` | Base 模型路径，不应指向旧的 `~/sylphos_models/...` |
| `rl_model_path` | RL 模型路径 |
| `device` | 诊断字段，通常为 `cuda`；不会直接传给 `AutoModel` 构造函数 |
| `python` | 服务进程 Python 版本 |
| `cosyvoice_importable` | 是否能导入 `cosyvoice.cli.cosyvoice` |
| `cosyvoice_loaded` | Base 模型是否已加载 |
| `default_prompt_wav` | 当前默认 zero-shot prompt wav 路径 |
| `default_prompt_wav_exists` | 默认 prompt wav 是否存在 |
| `prompt_dir` | `voice_id` 音色库目录 |
| `prompt_dir_exists` | 音色库目录是否存在 |
| `errors` | 预检或加载错误 |

排查要点：

- `cosyvoice_importable=false` 通常表示 `COSYVOICE_REPO` 或 `sys.path` 有问题；检查 `~/CosyVoice/cosyvoice/cli/cosyvoice.py` 是否存在。
- `cosyvoice_loaded=false` 通常表示模型路径、模型加载或依赖问题。
- `model_path` 应指向最终跑通路径 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B`。
- ONNX Runtime `libcudnn.so.8` 相关警告可以暂时忽略，只要 PyTorch CUDA 可用且 WAV 能生成。

### 13.5 WSL2 端 `/v1/tts` 验收命令

推荐使用 `--fail-with-body`，避免失败 JSON 被误当成 WAV：

```bash
curl --fail-with-body -w "
HTTP_STATUS=%{http_code}
CONTENT_TYPE=%{content_type}
SIZE=%{size_download}
TIME=%{time_total}
" \
-X POST http://127.0.0.1:9880/v1/tts \
-H "Content-Type: application/json" \
-d '{"text":"你好，我是 Sylphos。现在正在测试 CosyVoice 三服务。","model_version":"base"}' \
--output /tmp/sylphos_tts_test.wav

file /tmp/sylphos_tts_test.wav
ls -lh /tmp/sylphos_tts_test.wav
```

成功时应看到：

1. `HTTP_STATUS=200`。
2. `CONTENT_TYPE` 为 `audio/wav`。
3. `file /tmp/sylphos_tts_test.wav` 显示 `RIFF/WAVE`、`WAVE audio` 或类似 WAV 类型。
4. 文件大小大于 0。

如果 `file` 显示 `JSON text data`，说明服务端返回了错误 JSON，不是音频。失败时应查看 JSON 的 `error` / `errors` 字段。

### 13.6 Windows 端 Sylphos 调用测试

在 Windows PowerShell 中进入 Sylphos 仓库：

```powershell
cd <repo-root>
```

Base 模型测试：

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('主人，Sylphos 的本地语音合成服务已经连接成功。'); print(p)"
```

RL 模型测试：

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='rl', timeout_seconds=240, auto_play=True).speak('你好，我是 Sylphos。现在正在测试 RL 版本语音模型。'); print(p)"
```

说明：

1. `TTSClient` 默认调用 `http://127.0.0.1:9880/v1/tts`。
2. `auto_play=True` 时 Windows 端优先使用 `winsound` 后台播放，不再默认弹出播放器窗口。
3. 如果 `winsound` 失败，会 fallback 到 `default_app`。
4. `speak()` 返回生成的临时 WAV 文件路径。
5. 临时 WAV 通常位于：`<temporary-sylphos-tts-dir>`。

### 13.7 `voice_id` 音色切换

音色库目录：

```text
~/sylphos_services/cosyvoice3/prompts
```

每个音色使用一对文件：

```text
Kerrigan.wav
Kerrigan.txt

official.wav
official.txt
```

`voice_id="Kerrigan"` 会解析到：

```text
~/sylphos_services/cosyvoice3/prompts/Kerrigan.wav
~/sylphos_services/cosyvoice3/prompts/Kerrigan.txt
```

要求和建议：

1. `.txt` 必须是 `.wav` 中实际说的话，尽量逐字一致。
2. 参考音频建议 3-10 秒，单人、安静、无背景音乐、语速自然。
3. 当前 `voice_id` 机制默认查找 `.wav` 和 `.txt` 文件。
4. 即使某些 `.ogg` 改名 `.wav` 可能被底层解码器识别，也不建议长期依赖此行为。推荐使用 `ffmpeg` 转成真正 WAV：

```bash
ffmpeg -y -i input.ogg -ac 1 -ar 16000 Kerrigan.wav
# 或
ffmpeg -y -i input.ogg -ac 1 -ar 24000 Kerrigan.wav
```

Windows PowerShell 测试 Kerrigan 音色：

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('你好，我正在使用 Kerrigan 音色。', voice_id='Kerrigan'); print(p)"
```

切回官方音色：

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=240, auto_play=True).speak('你好，我现在切回官方默认音色。', voice_id='official'); print(p)"
```

临时换音色不需要重启服务，只要请求传不同 `voice_id` 即可。修改 `COSYVOICE_PROMPT_DIR` 环境变量本身需要重启服务。

### 13.8 `prompt_wav` / `prompt_text` 临时覆盖

除了 `voice_id`，也可以直接传 `prompt_wav` / `prompt_text`：

```json
{
  "text": "你好，我正在测试临时音色。",
  "model_version": "base",
  "prompt_wav": "~/sylphos_services/cosyvoice3/prompts/Kerrigan.wav",
  "prompt_text": "这里写 Kerrigan.wav 中实际说的话"
}
```

优先级：

1. 请求体 `prompt_wav` / `prompt_text`。
2. 请求体 `voice_id`。
3. 环境变量 `COSYVOICE_PROMPT_WAV` / `COSYVOICE_PROMPT_TEXT`。
4. 内置默认 `COSYVOICE_REPO/asset/zero_shot_prompt.wav` 和默认 prompt text。

默认 `prompt_text`：

```text
You are a helpful assistant.<|endofprompt|>希望你以后能够做的比我还好呦。
```

### 13.9 长文本测试与多段拼接

CosyVoice 对长文本可能会内部分段，generator 会 yield 多个 `tts_speech` 片段。服务端现在会完整消费 generator，并拼接所有音频片段后返回完整 WAV。

之前曾出现只播放到“汝之身托吾麾下”后截断的问题，原因是服务端只返回了第一段；现在已修复。上层 Sylphos 未来仍可以按句子做更细粒度分段，以便控制延迟、进度和打断，但服务端应能处理长文本并返回完整音频。

Windows PowerShell 长文本测试：

```powershell
.\.venv\Scripts\python.exe -c "from sylphos.voice.tts import TTSClient; p=TTSClient(model_version='base', timeout_seconds=300, auto_play=True).speak('1.温柔正确的人总是难以生存，因为这世界既不温柔，也不正确。2.我是毁灭世界，然后创造世界的人。3.宣告，汝之身托吾麾下。吾之命运附汝剑上，响应圣杯之召唤，遵从这意志、道理者，回应我！4.倘若出生于东海的我是无名小卒的话，那么被我砍倒的你到底又是哪根地上的葱呢。', voice_id='Kerrigan'); print(p)"
```

测试时要听最后一句是否完整播放。如果只播放前半段，说明多段拼接逻辑有问题。

### 13.10 当前已确认通过的能力

用户本机已经确认：

- 默认音色可用。
- `voice_id='Kerrigan'` 可用。
- Base 模型可用。
- RL 模型可用。
- 长文本多段生成拼接可用。
- Windows 端 `auto_play=True` 可以通过音箱直接播放。
- `/health`、`/v1/tts`、Windows `TTSClient` 端到端链路可用。

## 14. 最终合并前检查清单

合并 PR #18 前，按最终跑通路径逐项确认：

- [ ] WSL2 服务可以启动。
- [ ] `/health` 返回 `cosyvoice_importable=true`。
- [ ] `/health` 返回 `cosyvoice_loaded=true`。
- [ ] `/health` 中 `model_path` 指向 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B`。
- [ ] `/health` 中 `rl_model_path` 指向 `~/CosyVoice/pretrained_models/Fun-CosyVoice3-0.5B-rl`。
- [ ] Base 模型 `/v1/tts` 返回 `audio/wav`。
- [ ] RL 模型 `/v1/tts` 返回 `audio/wav`。
- [ ] Windows `TTSClient` 可以播放 Base。
- [ ] Windows `TTSClient` 可以播放 RL。
- [ ] Windows 端 `auto_play=True` 直接通过音箱播放，不弹出默认播放器窗口。
- [ ] `voice_id=Kerrigan` 测试通过。
- [ ] `voice_id=official` 可以切回默认/官方音色。
- [ ] 长文本最后一句完整播放。
- [ ] 失败请求返回 JSON 和非 200 状态码。
- [ ] 文档中的路径和实际路径一致。

可选基础环境复核：

- [ ] Windows 和 WSL2 中 `nvidia-smi` 正常。
- [ ] `cosyvoice3` Conda 环境已创建并激活。
- [ ] PyTorch `2.8.0` + CUDA `12.8` 测试通过。
- [ ] `~/CosyVoice` 官方仓库存在。
- [ ] `CosyVoice-ttsfrd` wheel 已安装，日志可出现 `use ttsfrd frontend`。
- [ ] `~/sylphos_services/cosyvoice3/prompts` 中的音色 `.wav` / `.txt` 成对存在。

---

## 15. 小结

通过以上步骤，CosyVoice3 被部署在 WSL2 Ubuntu 中，使用 Conda 管理 Python 3.10 环境，并通过 PyTorch CUDA 调用 GPU 完成语音合成。模型目录使用 `Fun-CosyVoice3-0.5B` 作为 Base 标准目录，并通过复制为 `Fun-CosyVoice3-0.5B-rl` 后替换 `llm.pt` 启用 RL 版本，便于服务端按请求参数切换。FastAPI 服务监听 `9880` 端口，Windows Sylphos 主程序通过 HTTP 调用 `/v1/tts`，传入文本与模型版本，接收生成音频后保存到 Windows 临时目录，并默认通过 `winsound` 在后台播放。

该架构将高负载的语音合成推理放在 WSL2 GPU 环境中，将 Sylphos 主程序保留在 Windows 端运行，既便于利用本机 GPU 性能，也便于 Windows 桌面应用直接集成语音播放能力。
