
import os, time, sys
os.chdir(r"D:\dshwork\bili-simul")
sys.path.insert(0, "server")
from app.config import load
from app.backends.tts import VoxCPMBackend, RefVoice
cfg = load(); cfg.voxcpm_optimize = False
eng = VoxCPMBackend(cfg)
ref = RefVoice(path_24k="data/samples/zh.wav", path_16k="data/samples/zh.wav", seconds=9.0,
               text="今天我们来聊一聊这个新版本到底值不值得升级。先说结论，我觉得大部分人现在还不必着急。")
t0=time.time(); eng.load(); print("load %.1fs" % (time.time()-t0), flush=True)
for i, t in enumerate(["你好，这是音色克隆测试。", "看那个贴纸，怎么办，对不起。"]):
    t0=time.time(); pcm = eng.synth(t, "zh", ref)
    print("synth %d: %.2fs -> %.2fs audio RTF %.2f" % (i, time.time()-t0, len(pcm)/eng.sr, (time.time()-t0)/max(len(pcm)/eng.sr,0.01)), flush=True)
