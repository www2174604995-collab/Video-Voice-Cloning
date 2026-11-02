
import time, sys
sys.path.insert(0, "server")
import torch
from windextts.models.gpt import UnifiedVoice
_orig = UnifiedVoice.generate
def _gen(self, *a, **kw):
    kw["use_cuda_graph"] = False
    return _orig(self, *a, **kw)
UnifiedVoice.generate = _gen

from windextts.inference import WIndexTTS
t0 = time.time()
e = WIndexTTS(weights_dir="data/models/indextts2", device="cuda", dtype=torch.float16, low_vram=True, enable_w4a16=True)
print("construct %.1fs" % (time.time()-t0), flush=True)
torch.cuda.reset_peak_memory_stats()
for i, txt in enumerate(["你好，这是音色克隆测试。", "怎么办，对不起。"]):
    t0 = time.time()
    sr, wav = e.infer(spk_audio_prompt="data/samples/zh.wav", text=txt, lang="ZH",
                      cfm_steps=8, num_beams=1, max_mel_tokens=110, max_text_tokens_per_segment=30)
    dt = time.time()-t0
    arr = wav.detach().cpu().numpy().reshape(-1)
    print("call %d: %.2fs audio in %.2fs RTF %.2f peak %.2fGB" % (i, len(arr)/sr, dt, dt/max(len(arr)/sr,0.01), torch.cuda.max_memory_allocated()/1e9), flush=True)
