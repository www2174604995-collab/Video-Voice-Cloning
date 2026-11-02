
import sys, time, os
sys.path.insert(0, "server")
os.environ.setdefault("COQUI_TOS_AGREED", "1")
import torch, numpy as np
from app.config import load
from app.backends.tts import XTTS, RefVoice

eng = XTTS(load())
eng.load()
m = eng._tts.synthesizer.tts_model
model_cfg = eng._tts.synthesizer.tts_config
ref = "data/samples/zh.wav"

t0 = time.time()
gpt_cond, spk_emb = m.get_conditioning_latents(audio_path=[ref])
print("conditioning (cold) %.2fs" % (time.time() - t0))

texts = [
 "Today we are going to talk about whether this new version is worth upgrading.",
 "I think most people do not need to rush.",
 "All right, that is it for this video.",
 "So if you are only doing office work, the previous generation is enough.",
]
for i, text in enumerate(texts):
    t0 = time.time()
    out = m.inference(
        text, "en", gpt_cond, spk_emb,
        temperature=0.65, length_penalty=1.0, repetition_penalty=2.0,
        top_k=50, top_p=0.8, enable_text_splitting=True,
    )
    wav = np.asarray(out["wav"], dtype=np.float32).reshape(-1)
    dt = time.time() - t0
    print("call %d: %.2fs audio in %.2fs  RTF %.2f" % (i, len(wav)/24000, dt, dt/max(len(wav)/24000, 0.01)))
print("peak vram %.2f GB" % (torch.cuda.max_memory_allocated()/1e9))
