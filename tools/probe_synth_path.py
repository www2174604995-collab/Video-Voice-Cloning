
import sys, time, os
sys.path.insert(0, "server")
os.environ.setdefault("COQUI_TOS_AGREED", "1")
import numpy as np
from app.config import load
from app.backends.tts import XTTS, RefVoice

eng = XTTS(load())
t0 = time.time(); eng.load(); print("load %.1fs" % (time.time()-t0), eng.detail, flush=True)
print("tts_model:", type(eng._tts.synthesizer.tts_model).__name__, flush=True)
ref = RefVoice(path_24k="data/samples/zh.wav", path_16k="data/samples/zh.wav", seconds=9.0)
for i, text in enumerate(["Today let us talk about this new version.", "I think most people do not need to rush."]):
    t0 = time.time()
    pcm = eng.synth(text, "en", ref)
    print("synth %d: %.2fs audio in %.2fs" % (i, len(pcm)/eng.sr, time.time()-t0), flush=True)
print("done", flush=True)
