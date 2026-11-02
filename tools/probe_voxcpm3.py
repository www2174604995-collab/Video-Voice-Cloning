
import os, sys, time
os.chdir(r"D:\dshwork\bili-simul")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
import numpy as np, torch, soundfile as sf
from voxcpm import VoxCPM
def log(*a): print(*a, flush=True)

t0 = time.time()
m = VoxCPM.from_pretrained("data/models/voxcpm", device="cuda")
log("load %.1fs  vram %.2fGB" % (time.time()-t0, torch.cuda.memory_allocated()/1e9))
for i, text in enumerate(["你好，这是音色克隆测试。", "看那个贴纸，怎么办，对不起。"]):
    t0 = time.time()
    wav = m.generate(text=text, prompt_wav_path="data/samples/zh.wav", cfg_value=2.0,
                     inference_timesteps=10, normalize=True, denoise=False, retry_badcase=False)
    dt = time.time()-t0
    wav = np.asarray(wav, dtype=np.float32).reshape(-1)
    log("call %d: %.2fs audio in %.2fs RTF %.2f peak %.2fGB" % (i, len(wav)/16000, dt, dt/max(len(wav)/16000,0.01), torch.cuda.max_memory_allocated()/1e9))
sf.write("data/out/voxcpm_zh.wav", wav, 16000)
log("saved data/out/voxcpm_zh.wav")
