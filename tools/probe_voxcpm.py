
import os, sys, time
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.chdir(r"D:\dshwork\bili-simul")

import numpy as np, torch, soundfile as sf
from voxcpm import VoxCPM

t0 = time.time()
m = VoxCPM.from_pretrained("openbmb/VoxCPM-0.5B", device="cuda")
print("load %.1fs" % (time.time()-t0), flush=True)
print("attrs:", [a for a in dir(m) if "sr" in a.lower() or "rate" in a.lower()], flush=True)

for i, text in enumerate(["你好，这是音色克隆测试。", "看那个贴纸，怎么办，对不起。"]):
    t0 = time.time()
    wav = m.generate(text=text, prompt_wav_path="data/samples/zh.wav", cfg_value=2.0, inference_timesteps=10, normalize=True, denoise=False)
    dt = time.time()-t0
    wav = np.asarray(wav, dtype=np.float32).reshape(-1)
    print("call %d: %.2fs audio in %.2fs RTF %.2f peak %.2fGB" % (i, len(wav)/16000, dt, dt/max(len(wav)/16000,0.01), torch.cuda.max_memory_allocated()/1e9), flush=True)
sf.write("data/out/voxcpm_zh.wav", wav, 16000)
print("saved data/out/voxcpm_zh.wav", flush=True)
