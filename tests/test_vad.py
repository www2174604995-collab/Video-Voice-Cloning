
"""Sanity checks for the streaming segmenter (no models needed)."""
import sys, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))

from app.vad import StreamSegmenter

SR = 16000


def speech(seconds, amp=0.25):
    n = int(SR * seconds)
    t = np.arange(n) / SR
    # crude voiced signal: 180 Hz + noise, envelope gated
    x = 0.6 * np.sin(2 * np.pi * 180 * t) + 0.25 * np.random.randn(n).astype(np.float32) * 0.3
    x *= amp * 2
    return x.astype(np.float32)


def silence(seconds):
    return (np.random.randn(int(SR * seconds)).astype(np.float32) * 0.0008)


def run(parts):
    seg = StreamSegmenter(sr=SR, min_speech=0.5, max_segment=6.0, end_silence=0.32)
    out = []
    t = 0.0
    for kind, dur in parts:
        block = speech(dur) if kind == "s" else silence(dur)
        # feed in 100 ms batches, like the browser does
        step = int(0.1 * SR)
        for i in range(0, len(block), step):
            chunk = block[i:i + step]
            if len(chunk) < step // 2:
                break
            t1 = t + len(chunk) / SR
            out.extend(seg.feed(chunk, t, t1, 1.0))
            t = t1
    return out, t


def main():
    parts = [("q", 0.5), ("s", 2.0), ("q", 0.8), ("s", 1.5), ("q", 0.9), ("s", 7.5), ("q", 1.0)]
    segs, total = run(parts)
    print("stream: %.2fs  segments: %d" % (total, len(segs)))
    ok = True
    for i, s in enumerate(segs):
        print("  #%d  t=%.2f..%.2f  dur=%.2f  rms=%.3f" % (i, s.t0, s.t1, s.duration, float(np.sqrt(np.mean(s.audio**2)))))
        if s.duration < 0.4 or s.t1 <= s.t0:
            ok = False
        if i and s.t0 < segs[i - 1].t1 - 0.05:
            print("   !! overlap with previous segment")
            ok = False
    # expected: 3 utterances, the 7.5 s one hard-cut into >=2 chunks
    if len(segs) < 4:
        print("expected at least 4 segments (long one must be split)")
        ok = False
    if segs[-1].t1 > total + 0.05:
        print("segment extends past the stream")
        ok = False

    # rate != 1 mapping
    seg = StreamSegmenter(sr=SR, min_speech=0.5, max_segment=6.0, end_silence=0.3)
    out = []
    t = 10.0
    for _ in range(20):
        out.extend(seg.feed(speech(0.1), t, t + 0.1, 2.0))
        t += 0.1
    print("rate=2: %d segments, first t0=%.2f (video clock should run 2x slower than audio)" % (len(out), out[0].t0 if out else -1))
    if out and not (out[0].t0 >= 9.9):
        ok = False

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
