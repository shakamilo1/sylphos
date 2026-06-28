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
