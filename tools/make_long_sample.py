
import sys, os, wave, numpy as np
sys.path.insert(0, r"D:\dshwork\bili-simul\server")
from app.backends.tts import SapiTTS
from app.config import Config

TEXT = (
 "今天我们来聊一聊这个新版本到底值不值得升级。先说结论，我觉得大部分人现在还不必着急。"
 "它的性能提升确实很明显，但是功耗也跟着上去了。那如果你只是日常办公，上一代其实完全够用。"
 "好了，这期视频就到这里，我们下期再见。"
)
t = SapiTTS(Config())
pcm = t.synth(TEXT, "zh")
from app import audio as A
pcm16 = A.resample(pcm, t.sr, 16000)
out = r"D:\dshwork\bili-simul\data\samples\zh_long.wav"
os.makedirs(os.path.dirname(out), exist_ok=True)
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes((np.clip(pcm16, -1, 1) * 32767).astype("<i2").tobytes())
print("wrote", out, round(len(pcm16) / 16000, 1), "s @ 16000")
