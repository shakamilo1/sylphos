import os
import time
import numpy as np
import sounddevice as sd
import importlib.resources as ir
from openwakeword.model import Model

DEVICE = 1                  # 设备编号

INPUT_RATE = 44100          # 设备默认采样率
TARGET_RATE = 16000
FRAME = 4410                # 0.1s @ 44.1k
THRESHOLD = 0.2

# 重采样
try:
    from samplerate import resample
    def to_16k(x):
        return resample(x, TARGET_RATE / INPUT_RATE, "sinc_fastest").astype(np.float32)
except Exception:
    from scipy.signal import resample_poly
    import math
    g = math.gcd(int(INPUT_RATE), int(TARGET_RATE))
    up = TARGET_RATE // g
    down = int(INPUT_RATE) // g
    def to_16k(x):
        return resample_poly(x, up, down).astype(np.float32)

models_dir = str(ir.files("openwakeword") / "resources" / "models")
jarvis = os.path.join(models_dir, "hey_jarvis_v0.1.onnx")
#jarvis = os.path.join(models_dir, "seer_fongss.onnx")
print("Using model:", jarvis)
print(sd.query_devices())
print(sd.query_hostapis())

model = Model(
    inference_framework="onnx",
    wakeword_models=[jarvis],
)

last_print = time.time()

def cb(indata, frames, time_info, status):
    global last_print
    if status:
        print("STATUS:", status)

    # 1) 输入 float32 [-1, 1]
    audio = indata[:, 0].astype(np.float32)

    # 2) 重采样到 16k float32
    audio16k = to_16k(audio)

    # 3) 转成 int16 PCM
    audio16k_i16 = np.clip(audio16k * 32768.0, -32768, 32767).astype(np.int16)

    scores = model.predict(audio16k_i16)

    # 每秒打印一次最高分
    now = time.time()
    if now - last_print >= 1.0:
        max_name = max(scores, key=scores.get)
        max_score = scores[max_name]
        print(f"[max] {max_name}: {max_score:.3f}")
        last_print = now

    # 真正触发
    max_name = max(scores, key=scores.get)
    max_score = scores[max_name]
    if max_score >= THRESHOLD:
        print(f"🔥 DETECTED: {max_name} score={max_score:.3f}")

with sd.InputStream(
    device=DEVICE,
    samplerate=INPUT_RATE,
    channels=1,
    blocksize=FRAME,
    dtype="float32",
    callback=cb,
):
    print("🎤 Listening for 'hey jarvis'... (Ctrl+C to stop)")
    while True:
        sd.sleep(1000)
