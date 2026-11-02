"""Offline video dubbing CLI — thin wrapper around app.dubbing.

    python tools/dub_video.py --video in.mp4 --ref ano.wav --target same --tts voxcpm
    python tools/dub_video.py --video in.mp4 --ref ano.wav --target same --tts indextts
"""
from __future__ import annotations

import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "server"))

from app.dubbing import dub_video  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--ref", required=True, help="reference clip of the voice to clone")
    ap.add_argument("--out", default="")
    ap.add_argument("--target", default="same", help="same | zh | en | ja ...")
    ap.add_argument("--tts", default="voxcpm")
    ap.add_argument("--bg", type=float, default=0.0)
    ap.add_argument("--asr-model", default="")
    ap.add_argument("--srt", default="", help="字幕文件（有字幕就不做识别和翻译）")
    ap.add_argument("--vc", action="store_true", help="再用 Seed-VC 把音色换成参考音")
    args = ap.parse_args()

    out = args.out or os.path.splitext(args.video)[0] + ".dub.mp4"
    started = time.time()
    last = {"t": 0.0}

    def report(stage: str, done: int, total: int, msg: str) -> None:
        now = time.time()
        if stage == "dub" and now - last["t"] < 0.5 and done != total:
            return
        last["t"] = now
        if total:
            print("[%s] %d/%d  %s" % (stage, done, total, msg), flush=True)
        else:
            print("[%s] %s" % (stage, msg), flush=True)

    print("[1/5] decoding + loading models ...", flush=True)
    dub_video(args.video, args.ref, out, target=args.target, bg=args.bg,
              tts=args.tts, asr_model=args.asr_model or None,
              vc=True if args.vc else None, subtitles=args.srt or None, progress=report)
    print("done in %.0f s -> %s" % (time.time() - started, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
