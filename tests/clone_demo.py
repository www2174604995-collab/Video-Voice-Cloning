
"""Clone a voice from a reference wav and say an arbitrary sentence.

    python tests/clone_demo.py --ref data/samples/zh.wav --text "Hello, this is a cloned voice." --lang en

Uses exactly the same backend class as the server, so this is also a smoke test.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")


def write_wav(path, x, sr):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def make_ref(path):
    from app.backends.tts import SapiTTS
    from app.config import Config

    tts = SapiTTS(Config())
    pcm = tts.synth("大家好，这是一段用来克隆音色的参考音频，大概需要几秒钟。", "zh")
    write_wav(path, pcm, tts.sr)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default="")
    ap.add_argument("--text", default="Hello, this is my voice speaking English.")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--out", default="data/out/clone.wav")
    args = ap.parse_args()

    ref = args.ref
    if not ref or not os.path.exists(ref):
        ref = os.path.join(ROOT, "data", "samples", "ref_zh.wav")
        print("no reference given, generating one with the offline voice:", ref)
        make_ref(ref)

    from app.backends.tts import RefVoice
    from app.config import load

    eng = __import__("app.backends.tts", fromlist=["XTTS"]).XTTS(load())
    print("loading XTTS ...")
    eng.load()
    voice = RefVoice(path_24k=ref, path_16k=ref, seconds=3.0)
    started = time.time()
    pcm = eng.synth(args.text, args.lang, voice)
    dur = len(pcm) / max(eng.sr, 1)
    elapsed = time.time() - started
    write_wav(args.out, pcm, eng.sr)
    print("saved %s  (%.2fs audio in %.2fs, RTF %.2f)" % (args.out, dur, elapsed, elapsed / max(dur, 0.01)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
