
import os, sys, time
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.chdir(r"D:\dshwork\bili-simul")
import numpy as np, torch

def log(*a):
    print(*a, flush=True)

from voxcpm import VoxCPM
t0=time.time()
m = VoxCPM.from_pretrained("openbmb/VoxCPM-0.5B", device="cuda")
log("load %.1fs" % (time.time()-t0))
log("vram %.2f GB" % (torch.cuda.memory_allocated()/1e9))
for name, kw in [
    ("plain", dict(text="你好。")),
    ("short", dict(text="你好。", retry_badcase=False, inference_timesteps=8)),
]:
    t0=time.time()
    try:
        wav = m.generate(**kw)
        dt=time.time()-t0
        wav=np.asarray(wav,dtype=np.float32).reshape(-1)
        log("%s: %.2fs audio in %.2fs RTF %.2f" % (name, len(wav)/16000, dt, dt/max(len(wav)/16000,0.01)))
    except Exception as e:
        log("%s FAILED %s %s" % (name, type(e).__name__, str(e)[:200]))
