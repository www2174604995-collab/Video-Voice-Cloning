
import time, sys, os
sys.path.insert(0, "server")
import torch
W = "data/models/indextts2"
from windextts.inference import WIndexTTS
t0 = time.time()
e = WIndexTTS(weights_dir=W, device="cuda", dtype=torch.float16, low_vram=True, enable_w4a16=True)
print("construct %.1fs" % (time.time()-t0), flush=True)
torch.cuda.reset_peak_memory_stats()
t0 = time.time()
sr, wav = e.infer(spk_audio_prompt="data/samples/zh.wav", text="你好，这是音色克隆测试。", lang="ZH",
                  cfm_steps=8, num_beams=1, max_mel_tokens=160, max_text_tokens_per_segment=40)
dt = time.time()-t0
arr = wav.detach().cpu().numpy().reshape(-1)
print("infer %.2fs -> %.2fs @%d RTF %.2f peak %.2f GB" % (dt, len(arr)/sr, sr, dt/max(len(arr)/sr,0.01), torch.cuda.max_memory_allocated()/1e9), flush=True)
