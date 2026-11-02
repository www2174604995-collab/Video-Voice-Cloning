"""Synthesize one line with a given engine and reference voice.

    python tools/tts_once.py --text "测试一句话。" --ref data/input/ano_ref.wav --tts indextts --out out.wav
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

from app import audio as A  # noqa: E402
from app.backends import build  # noqa: E402
from app.backends.tts import RefVoice  # noqa: E402
from app.config import load  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--ref-text", default="")
    ap.add_argument("--tts", default="indextts")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--out", default="out.wav")
    ap.add_argument("--timesteps", type=int, default=0)
    ap.add_argument("--cfg", type=float, default=0.0)
    ap.add_argument("--ref-seconds", type=float, default=0.0)
    args = ap.parse_args()

    cfg = load()
    cfg.tts = args.tts
    if args.timesteps:
        cfg.voxcpm_timesteps = args.timesteps
    if args.cfg:
        cfg.voxcpm_cfg = args.cfg
    if args.ref_seconds:
        from app.dubbing import prepare_ref

        args.ref = prepare_ref(args.ref, args.ref_seconds)
        print("ref trimmed (%.0fs) -> %s" % (args.ref_seconds, args.ref), flush=True)
    b = build(cfg)
    print("warmup:", " | ".join(b.warmup()), flush=True)
    text = args.ref_text
    if not text:
        txt = args.ref + ".txt"
        if os.path.isfile(txt):
            text = open(txt, encoding="utf-8").read().strip()
    ref = RefVoice(path_24k=args.ref, path_16k=args.ref, seconds=20.0, text=text)
    pcm = b.tts.synth(args.text, args.lang, ref)
    A.write_wav(args.out, pcm, int(getattr(b.tts, "sr", 24000)))
    print("saved %s (%.2fs @ %d)" % (args.out, len(pcm) / getattr(b.tts, "sr", 24000), getattr(b.tts, "sr", 24000)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
