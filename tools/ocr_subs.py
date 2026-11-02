"""Read burned-in subtitles with OCR and turn them into an SRT."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "server"))


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_frames(video: str, outdir: str, fps: float, band: float) -> int:
    vf = "fps=%s,crop=iw:ih*%s:0:ih*%s" % (fps, band, 1.0 - band)
    cmd = [ffmpeg(), "-y", "-v", "error", "-i", video, "-vf", vf,
           os.path.join(outdir, "%05d.png")]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[:300])
    return len([f for f in os.listdir(outdir) if f.endswith(".png")])


def srt_time(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def similar(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a, b).ratio()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--band", type=float, default=0.30)
    ap.add_argument("--min-score", type=float, default=0.6)
    args = ap.parse_args()
    out = args.out or os.path.join(os.path.dirname(args.video) or ".", "subs.srt")

    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    tmp = tempfile.mkdtemp(prefix="ocr-")
    print("[1/3] extracting frames at %.1f fps ..." % args.fps, flush=True)
    n = extract_frames(args.video, tmp, args.fps, args.band)
    print("      %d frames" % n, flush=True)

    print("[2/3] OCR ...", flush=True)
    cues = []
    for i, name in enumerate(sorted(os.listdir(tmp))):
        path = os.path.join(tmp, name)
        t = i / args.fps
        result = engine(path)
        rows = result[0] if result and result[0] else []
        texts = []
        for box, txt, score in rows:
            if float(score) >= args.min_score and txt.strip():
                texts.append((min(p[1] for p in box), min(p[0] for p in box), txt.strip()))
        line = " ".join(x[2] for x in sorted(texts))
        if line and (not cues or similar(cues[-1]["text"], line) < 0.8):
            cues.append({"t0": t, "t1": t + 1.0 / args.fps, "text": line})
        elif line and cues:
            cues[-1]["t1"] = t + 1.0 / args.fps
            if len(line) > len(cues[-1]["text"]):
                cues[-1]["text"] = line
        if (i + 1) % 200 == 0:
            print("      %d/%d" % (i + 1, n), flush=True)
    print("[3/3] writing %s (%d cues)" % (out, len(cues)), flush=True)
    with open(out, "w", encoding="utf-8") as fh:
        for k, c in enumerate(cues, 1):
            fh.write("%d\n%s --> %s\n%s\n\n" % (k, srt_time(c["t0"]), srt_time(c["t1"]), c["text"]))
    for c in cues[:8]:
        print("  %.1f-%.1f  %s" % (c["t0"], c["t1"], c["text"]))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
