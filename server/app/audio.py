from __future__ import annotations

import io
import os
import wave
from math import gcd
from typing import Tuple

import numpy as np


def pcm16_to_f32(buf: bytes) -> np.ndarray:
    """Little-endian int16 PCM -> float32 in [-1, 1]."""
    if not buf:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(buf, dtype="<i2").astype(np.float32) / 32768.0


def f32_to_pcm16(x: np.ndarray) -> bytes:
    x = np.asarray(x, dtype=np.float32)
    np.clip(x, -1.0, 1.0, out=x)
    return (x * 32767.0).astype("<i2").tobytes()


def rms(x: np.ndarray) -> float:
    if x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))


def peak(x: np.ndarray) -> float:
    return float(np.max(np.abs(x))) if x.size else 0.0


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    if sr_in == sr_out or x.size == 0:
        return x
    try:  # scipy is optional but much better quality
        from scipy.signal import resample_poly  # type: ignore

        g = gcd(int(sr_in), int(sr_out))
        y = resample_poly(x, int(sr_out) // g, int(sr_in) // g)
        return y.astype(np.float32)
    except Exception:
        n_out = max(1, int(round(x.size * sr_out / sr_in)))
        idx = np.linspace(0.0, x.size - 1.0, n_out, dtype=np.float64)
        return np.interp(idx, np.arange(x.size, dtype=np.float64), x).astype(np.float32)


def normalize(x: np.ndarray, target: float = 0.85) -> np.ndarray:
    p = peak(x)
    if p < 1e-6:
        return x
    return np.clip(x * (target / p), -1.0, 1.0).astype(np.float32)


def trim_silence(x: np.ndarray, sr: int, thresh: float = 0.008, pad_ms: int = 80) -> np.ndarray:
    """Trim leading/trailing near-silence (keeps a little padding)."""
    if x.size == 0:
        return x
    frame = max(1, sr // 50)
    n = x.size // frame
    if n == 0:
        return x
    energy = np.abs(x[: n * frame].reshape(n, frame)).mean(axis=1)
    loud = np.where(energy > thresh)[0]
    if loud.size == 0:
        return x
    pad = int(sr * pad_ms / 1000)
    a = max(0, loud[0] * frame - pad)
    b = min(x.size, (loud[-1] + 1) * frame + pad)
    return x[a:b]


def wav_bytes(x: np.ndarray, sr: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(f32_to_pcm16(x))
    return buf.getvalue()


def write_wav(path: str, x: np.ndarray, sr: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(wav_bytes(x, sr))


def decode_audio(data: bytes, sr_out: int = 24000) -> Tuple[np.ndarray, int]:
    """Decode almost any audio container (mp3/ogg/webm/wav/m4a) to mono float32."""
    try:
        import av  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PyAV is required to decode compressed audio. Install it with: pip install av"
        ) from exc

    chunks = []
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=int(sr_out))
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1).astype(np.float32))
        for out in resampler.resample(None):
            if out is not None:
                chunks.append(out.to_ndarray().reshape(-1).astype(np.float32))
    if not chunks:
        return np.zeros(0, dtype=np.float32), sr_out
    return np.concatenate(chunks).astype(np.float32), sr_out
