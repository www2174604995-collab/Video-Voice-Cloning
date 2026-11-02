
import time, sys
sys.path.insert(0, "server")
import torch

# --- disable CUDA-graph decode (capture is pathologically slow on 4 GB cards) ---
from windextts.models.gpt import UnifiedVoice
_orig_generate = UnifiedVoice.generate
def _generate_no_graph(self, *a, **kw):
    kw["use_cuda_graph"] = False
    return _orig_generate(self, *a, **kw)
UnifiedVoice.generate = _generate_no_graph

from windextts.inference import WIndexTTS
W = "data/models/indextts2"
t0 = time.time()
e = WIndexTTS(weights_dir=W, device="cuda", dtype=torch.float16, low_vram=True)
print("construct %.1fs vram %.2fGB" % (time.time()-t0, torch.cuda.memory_allocated()/1e9), flush=True)
for i, txt in enumerate(["你好，这是音色克隆测试。", "看那个贴纸，怎么办，对不起。"]):
    t0 = time.time()
    sr, wav = e.infer(spk_audio_prompt="data/samples/zh.wav", text=txt, lang="ZH", cfm_steps=10, num_beams=1)
    dt = time.time()-t0
    arr = wav.detach().cpu().numpy().reshape(-1)
    print("call %d: %.2fs audio in %.2fs RTF %.2f peak %.2fGB" % (i, len(arr)/sr, dt, dt/max(len(arr)/sr,0.01), torch.cuda.max_memory_allocated()/1e9), flush=True)
