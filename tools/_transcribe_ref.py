
import sys, os, time
sys.path.insert(0, r"D:\dshwork\bili-simul\server")
os.chdir(r"D:\dshwork\bili-simul")
from app.config import load
from app.backends.asr import FasterWhisperASR

cfg = load()
cfg.asr_model = "tiny"
a = FasterWhisperASR(cfg)
import subprocess, numpy as np, imageio_ffmpeg
ff = imageio_ffmpeg.get_ffmpeg_exe()
raw = subprocess.run([ff,"-v","error","-i","data/input/ano_ref.wav","-ac","1","-ar","16000","-f","s16le","-"],capture_output=True).stdout
x = np.frombuffer(raw, dtype="<i2").astype(np.float32)/32768
t0=time.time(); r = a.transcribe(x, None)
print("asr %.1fs lang=%s: %s" % (time.time()-t0, r.lang, r.text[:80]), flush=True)
open("data/input/ano_ref.wav.txt","w",encoding="utf-8").write(r.text)
print("wrote txt")
