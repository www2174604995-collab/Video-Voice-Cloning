"""Speaker similarity between two clips (ECAPA cosine, 0..1; >0.75 = same voice).

    python tools/speaker_sim.py original.wav generated.wav
"""
from __future__ import annotations

import os
import sys

import numpy as np

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "server"))

from app import audio as A  # noqa: E402

MODEL_DIR = os.path.join(ROOT, "data", "models", "spkrec-ecapa")


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: speaker_sim.py a.wav b.wav")
        return 2
    import torch
    from speechbrain.inference.speaker import EncoderClassifier

    enc = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=MODEL_DIR,
        run_opts={"device": "cuda" if torch.cuda.is_available() else "cpu"},
    )

    def embed(path: str) -> np.ndarray:
        import subprocess

        import imageio_ffmpeg

        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", path,
               "-ac", "1", "-ar", "16000", "-f", "s16le", "-"]
        raw = subprocess.run(cmd, capture_output=True).stdout
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        wav = torch.from_numpy(x).unsqueeze(0).float().to(enc.device)
        with torch.no_grad():
            e = enc.encode_batch(wav).squeeze().cpu().numpy()
        e = e / (np.linalg.norm(e) + 1e-9)
        return e

    a, b = embed(sys.argv[1]), embed(sys.argv[2])
    score = float(np.dot(a, b))
    print("similarity: %.3f  (1.0 = identical voice, >0.75 = same speaker)" % score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
