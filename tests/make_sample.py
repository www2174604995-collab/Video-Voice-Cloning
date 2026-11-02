"""Create a 16 kHz mono sample (default: a Chinese sentence via edge-tts).

    python tests/make_sample.py data/samples/zh.wav --lang zh --text "今天我们来聊聊..."
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))

TEXT = {
    "zh": "今天我们来聊一聊这个新版本到底值不值得升级。先说结论，我觉得大部分人现在还不必着急。",
    "en": "Today we are going to talk about whether this new version is really worth upgrading to.",
}

VOICE = {"zh": "zh-CN-YunxiNeural", "en": "en-US-GuyNeural"}


def write_wav(path: str, samples: np.ndarray, sr: int) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


async def synth(text: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--lang", default="zh", choices=list(TEXT))
    ap.add_argument("--text", default="")
    args = ap.parse_args()

    text = args.text or TEXT[args.lang]
    print("synthesizing:", text[:40], "...")
    data = asyncio.run(synth(text, VOICE[args.lang]))

    from app import audio as A

    pcm, sr = A.decode_audio(data, 16000)
    write_wav(args.out, pcm, 16000)
    print(f"wrote {args.out}: {len(pcm) / 16000:.1f}s @16k")
    return 0


if __name__ == "__main__":
    sys.exit(main())
