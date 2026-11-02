"""Build the best possible cloning reference from a noisy source.

Instead of one contiguous window, this picks the *best sounding speech
segments* (high SNR, no music, clean onsets), concatenates them and normalises
loudness. Multi-segment references clone more faithfully than a single window.

    python tools/ref_best.py --src ano.mp4 --out data/input/ano_best.wav
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
from app.dubbing import decode_audio  # noqa: E402
from app.vad import StreamSegmenter  # noqa: E402

SR = 16000
MIX = 24000


def demucs_vocals(path: str) -> str:
    """Use an external demucs install if it exists (removes BGM)."""
    for py in (
        os.path.join(ROOT, "seed-vc", ".venv-vc", "bin", "python"),
        os.path.join(ROOT, ".venv", "Scripts", "python.exe"),
    ):
        if not os.path.isfile(py):
            continue
        outdir = tempfile.mkdtemp(prefix="dm-")
        try:
            proc = subprocess.run(
                [py, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs", "-o", outdir, path],
                capture_output=True, text=True,
            )
        except Exception:
            continue
        if proc.returncode != 0:
            print("[demucs] failed: %s" % (proc.stderr or "")[-200:], flush=True)
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        cand = os.path.join(outdir, "htdemucs", stem, "vocals.wav")
        if os.path.isfile(cand):
            print("[demucs] vocals separated", flush=True)
            return cand
    return path


def speech_segments(x: np.ndarray):
    seg = StreamSegmenter(sr=SR, frame_ms=30, min_speech=0.6, max_segment=8.0,
                          end_silence=0.30, energy_threshold=0.0)
    out, t, step = [], 0.0, int(0.1 * SR)
    for i in range(0, len(x), step):
        chunk = x[i:i + step]
        if chunk.size < step // 2:
            break
        t1 = t + chunk.size / SR
        out.extend(seg.feed(chunk, t, t1, 1.0))
        t = t1
    silence = np.zeros(int(1.0 * SR), dtype=np.float32)
    out.extend(seg.feed(silence, t, t + 1.0, 1.0))
    return out


def score_segment(audio: np.ndarray, floor: float) -> float:
    """Prefer loud, long, steady speech (high SNR-ish) over short noisy bits."""
    if audio.size < SR * 0.5:
        return 0.0
    rms = float(np.sqrt(np.mean(audio ** 2)) + 1e-9)
    snr = 20 * np.log10(max(rms, 1e-6) / max(floor, 1e-6))
    length = len(audio) / SR
    # penalise segments whose level wanders (mixed speech + music)
    frame = int(0.05 * SR)
    n = len(audio) // frame
    if n < 4:
        return 0.0
    levels = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    steadiness = 1.0 / (1.0 + float(np.std(levels) / (np.mean(levels) + 1e-9)))
    return (max(snr, 0.0) + 6.0) * min(length, 6.0) * steadiness


def build(src: str, out: str, seconds: float = 15.0, use_demucs: bool = True) -> str:
    tmp = src
    if use_demucs and not src.lower().endswith(".wav"):
        tmp = demucs_vocals(src)
    x = decode_audio(tmp, SR)
    segs = speech_segments(x)
    if not segs:
        raise SystemExit("no speech found")
    energies = np.array([np.sqrt(np.mean(s.audio ** 2)) for s in segs])
    floor = float(np.percentile(energies, 15))
    ranked = sorted(segs, key=lambda s: score_segment(s.audio, floor), reverse=True)
    print("segments: %d, floor %.4f" % (len(segs), floor), flush=True)

    picked, total = [], 0.0
    for s in ranked:
        if total >= seconds:
            break
        picked.append(s)
        total += s.duration
    picked.sort(key=lambda s: s.t0)

    gap = np.zeros(int(0.12 * SR), dtype=np.float32)
    parts = []
    for s in picked:
        a = np.array(s.audio, dtype=np.float32)
        fade = int(0.02 * SR)
        if a.size > 2 * fade:
            a[:fade] *= np.linspace(0, 1, fade)
            a[-fade:] *= np.linspace(1, 0, fade)
        parts.append(a)
        parts.append(gap)
    y = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    peak = float(np.max(np.abs(y))) or 1.0
    y = (y / peak * 0.9).astype(np.float32)
    A.write_wav(out, A.resample(y, SR, MIX), MIX)
    print("wrote %s  (%.1f s from %d segments)" % (out, len(y) / SR, len(picked)), flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--no-demucs", action="store_true")
    args = ap.parse_args()
    out = args.out or os.path.join(os.path.dirname(args.src) or ".", "ref_best.wav")
    build(args.src, out, args.seconds, use_demucs=not args.no_demucs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
