"""Build a clean reference clip for voice cloning from any video/audio.

    python tools/make_ref.py --video data/input/ano.mp4 --out data/input/ano_ref.wav --seconds 25

Steps: extract audio -> (optional) demucs vocal separation -> pick the most
speech-dense window -> normalize -> transcribe (for VoxCPM) -> write wav+txt.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

from app import audio as A  # noqa: E402


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def extract(path: str, sr: int, out: str, channels: int = 1) -> None:
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", path, "-vn", "-ac", str(channels),
           "-ar", str(sr), out]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:400])


def read_wav(path: str):
    import wave

    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def best_window(x: np.ndarray, sr: int, seconds: float) -> tuple[int, int]:
    """Pick the window with the most continuous speech energy."""
    win = int(seconds * sr)
    if len(x) <= win:
        return 0, len(x)
    frame = int(0.05 * sr)
    n = len(x) // frame
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    thr = max(0.01, float(np.percentile(rms, 70)) * 0.5)
    voiced = (rms > thr).astype(np.float32)
    k = max(1, win // frame)
    cum = np.concatenate([[0.0], np.cumsum(voiced)])
    scores = cum[k:] - cum[:-k]
    if len(scores) == 0:
        return 0, win
    idx = int(np.argmax(scores))
    start = idx * frame
    return start, min(len(x), start + win)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--seconds", type=float, default=25.0)
    ap.add_argument("--no-demucs", action="store_true")
    args = ap.parse_args()
    out = args.out or os.path.join(os.path.dirname(args.video) or ".", "ref.wav")

    tmp = tempfile.mkdtemp(prefix="makeref-")
    src44 = os.path.join(tmp, "src44.wav")
    print("[1/4] extracting audio ...", flush=True)
    extract(args.video, 44100, src44, channels=2)

    vocals = None
    if not args.no_demucs:
        print("[2/4] separating vocals (demucs) ...", flush=True)
        try:
            r = subprocess.run(
                [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
                 "-o", tmp, src44],
                capture_output=True, text=True,
            )
            cand = os.path.join(tmp, "htdemucs", "src44", "vocals.wav")
            if r.returncode == 0 and os.path.isfile(cand):
                vocals = cand
                print("      vocals separated", flush=True)
            else:
                print("      demucs failed, using the raw track: " +
                      (r.stderr or "")[-200:], flush=True)
        except Exception as exc:
            print("      demucs unavailable: %s" % exc, flush=True)

    print("[3/4] picking the cleanest speech window ...", flush=True)
    x, sr = read_wav(vocals or src44)
    start, end = best_window(x, sr, args.seconds)
    clip = x[start:end]
    peak = float(np.max(np.abs(clip))) or 1.0
    clip = (clip / peak * 0.9).astype(np.float32)
    clip24 = A.resample(clip, sr, 24000)
    A.write_wav(out, clip24, 24000)
    print("      %.1f s -> %s" % (len(clip24) / 24000, out), flush=True)

    print("[4/4] transcribing (for VoxCPM prompt_text) ...", flush=True)
    try:
        from app.config import load
        from app.backends.asr import FasterWhisperASR

        cfg = load()
        asr = FasterWhisperASR(cfg)
        res = asr.transcribe(A.resample(clip24, 24000, 16000), None)
        txt = out + ".txt"
        with open(txt, "w", encoding="utf-8") as fh:
            fh.write(res.text)
        print("      " + txt + "  ->  " + res.text[:60], flush=True)
    except Exception as exc:
        print("      asr skipped: %s" % exc, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
