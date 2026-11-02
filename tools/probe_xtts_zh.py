
import time, sys
sys.path.insert(0, "server")
import numpy as np
from app.config import load
from app.backends.tts import XTTS, RefVoice
c = load(); c.tts_device = "cpu"
e = XTTS(c); e.load()
ref = RefVoice(path_24k="data/samples/zh.wav", path_16k="data/samples/zh.wav", seconds=9.0)
for i, t in enumerate(["看那个贴纸，怎么办，对不起。", "我觉得大部分人现在还不必着急。"]):
    t0 = time.time(); pcm = e.synth(t, "zh", ref); dt = time.time()-t0
    print("zh %d: %.2fs audio in %.2fs RTF %.2f" % (i, len(pcm)/e.sr, dt, dt/max(len(pcm)/e.sr,0.01)), flush=True)
import wave
with wave.open("data/out/xtts_zh.wav","wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(e.sr)
    w.writeframes((np.clip(pcm,-1,1)*32767).astype("<i2").tobytes())
print("saved data/out/xtts_zh.wav")
