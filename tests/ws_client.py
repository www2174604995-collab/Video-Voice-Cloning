"""Stream a 16 kHz mono WAV into the engine and save the dubbed result.

Usage:
    python tests/ws_client.py data/samples/zh.wav --target en --out data/out/en.wav
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import wave

import numpy as np
import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server"))

from app.protocol import pack_client_frame, unpack_audio_frame  # noqa: E402


def read_wav(path: str):
    with wave.open(path, "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise SystemExit("need mono 16-bit wav")
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return data, sr


def write_wav(path: str, samples, sr: int = 24000):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


async def main_async(args) -> int:
    audio, sr = read_wav(args.wav)
    if sr != 16000:
        raise SystemExit("sample must be 16 kHz")
    url = args.url.rstrip("/")
    if not url.endswith("/ws"):
        url += "/ws"

    results = {"subs": [], "audio": [], "sr": 24000, "stats": []}

    async with websockets.connect(url, max_size=None) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "target_lang": args.target,
                    "source_lang": args.source,
                    "voice": args.voice,
                }
            )
        )

        async def receiver():
            while True:
                try:
                    msg = await ws.recv()
                except Exception:
                    return
                if isinstance(msg, bytes):
                    seg_id, t0, t1, frame_sr, pcm = unpack_audio_frame(msg)
                    results["audio"].append(pcm)
                    results["sr"] = frame_sr
                    print(f"  <- audio #{seg_id} {len(pcm) / frame_sr:.2f}s @ {frame_sr}Hz (video {t0:.1f}-{t1:.1f})")
                else:
                    data = json.loads(msg)
                    if data.get("type") == "subtitle":
                        results["subs"].append(data)
                        print(f"  <- sub t={data['t0']:.1f} {data['src']}  =>  {data['dst']}")
                    elif data.get("type") == "stat":
                        results["stats"].append(data)
                        eng = data.get("engine")
                        if eng and eng != results.get("last_engine"):
                            results["last_engine"] = eng
                            print(f"  <- voice engine: {eng}")
                    elif data.get("type") == "ready":
                        print("  <- ready:", json.dumps(data.get("backends"), ensure_ascii=False))
                    elif data.get("type") == "error":
                        print("  <- error:", data.get("message"))

        recv = asyncio.create_task(receiver())
        await asyncio.sleep(0.2)

        chunk = int(0.1 * sr)
        t = 0.0
        started = time.time()
        for start in range(0, len(audio), chunk):
            piece = audio[start : start + chunk]
            if piece.size < chunk // 2:
                break
            t1 = t + piece.size / sr
            await ws.send(pack_client_frame(int(t * 10), t, t1, piece))
            t = t1
            if not args.fast:
                await asyncio.sleep(piece.size / sr)
        print(f"  -> streamed {t:.1f}s of audio in {time.time() - started:.1f}s wall")

        await ws.send(json.dumps({"type": "end"}))
        await asyncio.sleep(args.drain)
        recv.cancel()

    if results["audio"]:
        joined = np.concatenate(results["audio"])
        write_wav(args.out, joined, results["sr"])
        print(f"saved {len(joined) / results['sr']:.1f}s of dubbed audio -> {args.out}")
    else:
        print("no audio came back")
    print(f"subtitles: {len(results['subs'])}")
    return 0 if results["subs"] or results["audio"] else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--url", default="ws://127.0.0.1:8765")
    ap.add_argument("--target", default="en")
    ap.add_argument("--source", default="auto")
    ap.add_argument("--voice", default="clone")
    ap.add_argument("--out", default="data/out/dub.wav")
    ap.add_argument("--fast", action="store_true", help="do not pace at realtime")
    ap.add_argument("--drain", type=float, default=6.0, help="seconds to wait for the tail")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
