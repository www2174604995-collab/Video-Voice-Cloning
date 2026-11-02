"""Generate N takes for a sentence and score how close each sounds to the reference.

Crude but dependency-free timbre metric (MFCC statistics + cosine). Use it to
compare base model vs LoRA checkpoints under identical conditions.

    python tools/eval_voice.py --ref data/input/ano.wav --n 3 --tag base
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "server"))

from app import audio as A  # noqa: E402
from app.backends import build  # noqa: E402
from app.backends.tts import RefVoice  # noqa: E402
from app.config import load  # noqa: E402
from app.dubbing import decode_audio  # noqa: E402

TEXT = "今天我们来聊一聊这个新版本的升级点。"


def timbre_vector(x: np.ndarray, sr: int) -> np.ndarray:
    """MFCC mean+std — a stable, cheap proxy for voice colour."""
    import librosa

    y = librosa.resample(np.asarray(x, dtype=np.float32), orig_sr=sr, target_sr=16000)
    mfcc = librosa.feature.mfcc(y=y, sr=16000, n_mfcc=20)
    vec = np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)])
    return vec / (np.linalg.norm(vec) + 1e-9)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--text", default=TEXT)
    ap.add_argument("--outdir", default="data/out")
    args = ap.parse_args()

    cfg = load()
    b = build(cfg)
    print(b.warmup()[0], flush=True)
    ref = RefVoice(path_24k=args.ref, path_16k=args.ref, seconds=40.0, text="")
    rv = timbre_vector(decode_audio(args.ref, 16000), 16000)

    scores = []
    best, best_score = None, -1.0
    for i in range(args.n):
        pcm = b.tts.synth(args.text, "zh", ref)
        sr = int(getattr(b.tts, "sr", 48000))
        pcm = np.asarray(pcm, dtype=np.float32)
        s = float(np.dot(timbre_vector(pcm, sr), rv))
        scores.append(s)
        path = os.path.join(args.outdir, "%s_%d.wav" % (args.tag, i))
        A.write_wav(path, pcm, sr)
        print("take %d: timbre %.3f  dur %.2fs -> %s" % (i, s, len(pcm) / sr, path), flush=True)
        if s > best_score:
            best, best_score = pcm, s

    A.write_wav(os.path.join(args.outdir, "%s_best.wav" % args.tag), best, sr)
    print("scores %s  mean %.3f  max %.3f" % (
        ["%.3f" % x for x in scores], float(np.mean(scores)), max(scores)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
