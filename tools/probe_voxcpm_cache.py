
import os, time
os.chdir(r"D:\dshwork\bili-simul")
import numpy as np, torch, soundfile as sf
from voxcpm import VoxCPM
def log(*a): print(*a, flush=True)

REF_TEXT = "今天我们来聊一聊这个新版本到底值不值得升级。先说结论，我觉得大部分人现在还不必着急。"
m = VoxCPM.from_pretrained("data/models/voxcpm", device="cuda")
t0 = time.time()
cache = m.tts_model.build_prompt_cache(prompt_text=REF_TEXT, prompt_wav_path="data/samples/zh.wav")
log("prompt cache %.2fs" % (time.time()-t0))

for steps in (10, 6):
    for i, text in enumerate(["你好，这是音色克隆测试。", "看那个贴纸，怎么办，对不起。"]):
        t0 = time.time()
        gen = m.tts_model._generate_with_prompt_cache(
            target_text=text, prompt_cache=cache, min_len=2, max_len=4096,
            inference_timesteps=steps, cfg_value=2.0,
            retry_badcase=False, retry_badcase_max_times=1,
            retry_badcase_ratio_threshold=6.0, streaming=False)
        wav, _, _ = next(gen)
        dt = time.time()-t0
        wav = wav.squeeze(0).cpu().numpy().reshape(-1)
        log("steps=%d call %d: %.2fs audio in %.2fs RTF %.2f peak %.2fGB" % (
            steps, i, len(wav)/16000, dt, dt/max(len(wav)/16000,0.01), torch.cuda.max_memory_allocated()/1e9))
        if steps == 10 and i == 0:
            sf.write("data/out/voxcpm_cache.wav", wav, 16000)
