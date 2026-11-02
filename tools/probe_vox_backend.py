
import os, time, threading
os.chdir(r"D:\dshwork\bili-simul")
import sys
sys.path.insert(0, "server")
from app.config import load
from app.backends.tts import VoxCPMBackend, RefVoice

cfg = load()
eng = VoxCPMBackend(cfg)
ref = RefVoice(path_24k="data/samples/zh.wav", path_16k="data/samples/zh.wav", seconds=9.0,
               text="今天我们来聊一聊这个新版本到底值不值得升级。先说结论，我觉得大部分人现在还不必着急。")

def work():
    t0=time.time(); eng.load(); print("load %.1fs" % (time.time()-t0), flush=True)
    t0=time.time(); pcm = eng.synth("你好，这是音色克隆测试。", "zh", ref)
    print("synth %.2fs -> %.2fs" % (time.time()-t0, len(pcm)/eng.sr), flush=True)

th = threading.Thread(target=work)
th.start(); th.join(timeout=180)
print("alive:", th.is_alive(), flush=True)
