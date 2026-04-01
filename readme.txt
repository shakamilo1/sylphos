创建 Sylphos 环境
在 CMD 或 Anaconda Prompt 中执行：

cd /d H:\sylphos
conda create -n sylphos -c conda-forge python=3.11
conda activate sylphos

安装环境
conda env update -f environment.yml --prune

自检（验证安装是否成功）
conda activate sylphos
python -c "import fastapi, sounddevice, webrtcvad, openwakeword, faster_whisper, orjson; print('Sylphos environment OK')"

输出：
Sylphos environment OK