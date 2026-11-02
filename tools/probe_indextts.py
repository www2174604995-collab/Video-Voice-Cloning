
import time, sys, os
sys.path.insert(0, "server")
os.environ.setdefault("COQUI_TOS_AGREED", "1")
import torch

print("cuda", torch.cuda.is_available())
try:
    from wetext import Normalizer
    n = Normalizer(lang="zh", operator="tn")
    print("wetext zh:", n.normalize("2024年，3.5%的人用了GPT-5。"))
except Exception as e:
    print("wetext FAILED:", type(e).__name__, str(e)[:200])

from windextts.inference import WIndexTTS
t0 = time.time()
e = WIndexTTS(weights_dir="data/models/indextts2", device="cuda", dtype=torch.float16, low_vram=True)
print("construct %.1fs" % (time.time()-t0), flush=True)
t0 = time.time()
try:
    e.warmup()
    print("warmup %.1fs" % (time.time()-t0), flush=True)
except Exception as ex:
    print("warmup skipped:", type(ex).__name__, str(ex)[:200], flush=True)
t0 = time.time()
sr, wav = e.infer(spk_audio_prompt="data/samples/zh.wav", text="你好，这是音色克隆测试。", lang="ZH", cfm_steps=12)
dt = time.time()-t0
arr = wav.detach().cpu().numpy().reshape(-1) if hasattr(wav, "detach") else wav
print("infer %.2fs -> %.2fs audio @%d Hz  RTF %.2f" % (dt, len(arr)/sr, sr, dt/max(len(arr)/sr, 0.01)), flush=True)
print("peak vram %.2f GB" % (torch.cuda.max_memory_allocated()/1e9))
