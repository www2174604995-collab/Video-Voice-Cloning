
import time, sys, os
sys.path.insert(0, "server")
import torch

W = "data/models/indextts2"
t0 = time.time()
from windextts.inference import WIndexTTS
e = WIndexTTS(weights_dir=W, device="cuda", dtype=torch.float16, low_vram=True, enable_w4a16=True)
print("construct int4 %.1fs  vram %.2f GB" % (time.time()-t0, torch.cuda.memory_allocated()/1e9), flush=True)
t0 = time.time()
sr, wav = e.infer(spk_audio_prompt="data/samples/zh.wav", text="你好，这是音色克隆测试。", lang="ZH", cfm_steps=10, num_beams=1)
dt = time.time()-t0
arr = wav.detach().cpu().numpy().reshape(-1)
print("infer %.2fs -> %.2fs @%d RTF %.2f  peak %.2f GB" % (dt, len(arr)/sr, sr, dt/max(len(arr)/sr,0.01), torch.cuda.max_memory_allocated()/1e9), flush=True)
